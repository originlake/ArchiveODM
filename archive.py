import yaml
import requests
import json
import subprocess

with open('config.yml', 'r') as fhand:
    config = yaml.safe_load(fhand)

def copy_images(src_image, tar_image):
    p = subprocess.run(["docker","run","quay.io/skopeo/stable:latest","copy", f"docker://{src_image}", f"docker://{tar_image}", "--all"])
    p.check_returncode()

def get_tags(repository):
    p = subprocess.run(["docker","run","quay.io/skopeo/stable:latest", "list-tags", f"docker://{repository}"], capture_output=True)
    p.check_returncode()
    return json.loads(p.stdout.decode('utf-8'))["Tags"]

def get_api_json(url):
    resp = requests.get(url, timeout=30)
    assert resp.ok, f"Failed to get results from {url}"
    return resp.json()

def is_diff(image1, image2):
    p = subprocess.run(["docker","run","quay.io/skopeo/stable:latest", "inspect", f"docker://{image1}", "--raw"], capture_output=True)
    p.check_returncode()
    image_info1 = json.loads(p.stdout.decode('utf-8'))
    p = subprocess.run(["docker","run","quay.io/skopeo/stable:latest", "inspect", f"docker://{image2}", "--raw"], capture_output=True)
    p.check_returncode()
    image_info2 = json.loads(p.stdout.decode('utf-8'))
    if "manifests" in image_info1 and "manifests" in image_info2:
        digest1 = [x for x in image_info1["manifests"] if x['platform']['architecture'] == "amd64"][0]
        digest2 = [x for x in image_info2["manifests"] if x['platform']['architecture'] == "amd64"][0]
    else:
        # TODO: handle this
        print("build without manifests, skip for now")
        return False
    return digest1 != digest2
    
def main():
    archieved_tags = get_tags(config["archive_repository"])
    odm_tags = get_tags(config["odm_repository"])
    latest_release = get_api_json(f"https://api.github.com/repos/{config['odm_git_repository']}/releases/latest")

    if latest_release['name'] not in archieved_tags:
        print(f"New release {latest_release['name']} published, start archiving the latest docker image")
        src_tag = latest_release['name'] if latest_release['name'] in odm_tags else 'latest'
        copy_images(f"{config['odm_repository']}:{src_tag}", f"{config['archive_repository']}:{latest_release['name']}")
        copy_images(f"{config['odm_repository']}:gpu", f"{config['archive_repository']}:gpu_{latest_release['name']}")
        print(f"Successfully archived the latest docker image to {config['archive_repository']}:{latest_release['name']}")
        return
    
    # docker image can be pushed later than release published
    if latest_release['name'] in odm_tags:
        if is_diff(f"{config['odm_repository']}:{latest_release['name']}", f"{config['archive_repository']}:{latest_release['name']}"):
            print(f"Detect different digests between odm and archived image of release {latest_release['name']}, start archiving")
            copy_images(f"{config['odm_repository']}:{latest_release['name']}", f"{config['archive_repository']}:{latest_release['name']}")
            # ignore gpu as it won't be tagged
            print(f"Successfully archived the latest docker image to {config['archive_repository']}:{latest_release['name']}")
            return

    print("No new release detected, exit")

if __name__ == "__main__":
    main()
    
