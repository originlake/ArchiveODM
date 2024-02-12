import os
import yaml
import requests
import json
import docker
import re
import datetime

DOCKER_HUB_USERNAME = os.environ.get("DOCKER_HUB_USERNAME")
DOCKER_HUB_TOKEN = os.environ.get("DOCKER_HUB_ACCESS_TOKEN")
SKOPEO_IMAGE = "quay.io/skopeo/stable:latest"
DATE_PATTERN = r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{6})\d*Z'
client = docker.from_env()

with open('config.yml', 'r') as fhand:
    config = yaml.safe_load(fhand)

def skopeo_run(args, capture_output=True):
    if capture_output:
        return client.containers.run(SKOPEO_IMAGE, command=args, remove=True).decode('utf-8')
    else:
        status = True
        container = client.containers.run(SKOPEO_IMAGE, command=args, detach=True)
        for line in container.logs(stream=True):
            print(line.decode('utf-8'), end='')
        if container.wait()['StatusCode'] != 0:
            print("Failed to run skopeo command")
            status = False
        container.remove()
        return status

def copy_images(src_image, tar_image):
    return skopeo_run(["copy", f"docker://{src_image}", f"docker://{tar_image}", "--all", f"--dest-creds={DOCKER_HUB_USERNAME}:{DOCKER_HUB_TOKEN}"], capture_output=False)

def get_tags(repository):
    res = skopeo_run(["list-tags", f"docker://{repository}"])
    return json.loads(res)["Tags"]

def get_api_json(url):
    resp = requests.get(url, timeout=30)
    assert resp.ok, f"Failed to get results from {url}"
    return resp.json()

def is_diff(image1, image2):
    res = skopeo_run(["inspect", f"docker://{image1}", "--raw"])
    image_info1 = json.loads(res)
    res = skopeo_run(["inspect", f"docker://{image2}", "--raw"])
    image_info2 = json.loads(res)
    if "manifests" in image_info1 and "manifests" in image_info2:
        digest1 = [x for x in image_info1["manifests"] if x['platform']['architecture'] == "amd64"][0]
        digest2 = [x for x in image_info2["manifests"] if x['platform']['architecture'] == "amd64"][0]
    else:
        # TODO: handle this
        print("build without manifests, skip for now")
        return False
    return digest1 != digest2

def is_newer(image1, image2):
    def get_date(date_str):
        match = re.search(DATE_PATTERN, date_str)
        if not match:
            return None
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        second = int(match.group(6))
        microsecond = int(match.group(7))
        return datetime.datetime(year, month, day, hour, minute, second, microsecond)
    res = skopeo_run(["inspect", f"docker://{image1}"])
    image_info1 = json.loads(res)
    date1 = get_date(image_info1['Created'])
    res = skopeo_run(["inspect", f"docker://{image2}"])
    image_info2 = json.loads(res)
    date2 = get_date(image_info2['Created'])
    if date1 is None or date2 is None:
        raise ValueError("Failed to get image creation date")
    return date1 > date2

def main():
    archieved_tags = get_tags(config["archive_repository"])
    odm_tags = get_tags(config["odm_repository"])
    latest_release = get_api_json(f"https://api.github.com/repos/{config['odm_git_repository']}/releases/latest")

    if latest_release['name'] not in archieved_tags:
        print(f"New release {latest_release['name']} published, start archiving the latest docker image")
        src_tag = latest_release['name'] if latest_release['name'] in odm_tags else 'latest'
        copy_status = copy_images(f"{config['odm_repository']}:{src_tag}", f"{config['archive_repository']}:{latest_release['name']}")
        gpu_copy_status = copy_images(f"{config['odm_repository']}:gpu", f"{config['archive_repository']}:gpu_{latest_release['name']}")
        if copy_status and gpu_copy_status:
            print(f"Successfully archived the latest docker image to {config['archive_repository']}:{latest_release['name']}")
        else:
            if not copy_status:
                print(f"Failed to archive the latest docker image to {config['archive_repository']}:{latest_release['name']}")
            if not gpu_copy_status:
                print(f"Failed to archive the latest docker image to {config['archive_repository']}:gpu_{latest_release['name']}")
        return

    # docker image can be pushed later than release published
    if latest_release['name'] in odm_tags:
        if is_diff(f"{config['odm_repository']}:{latest_release['name']}", f"{config['archive_repository']}:{latest_release['name']}") and \
            is_newer(f"{config['odm_repository']}:{latest_release['name']}", f"{config['archive_repository']}:{latest_release['name']}"):
            print(f"Detect different digests between odm and archived image of release {latest_release['name']}, start archiving")
            status = copy_images(f"{config['odm_repository']}:{latest_release['name']}", f"{config['archive_repository']}:{latest_release['name']}")
            # ignore gpu as it won't be tagged
            if status:
                print(f"Successfully archived the latest docker image to {config['archive_repository']}:{latest_release['name']}")
            else:
                print(f"Failed to archive the latest docker image to {config['archive_repository']}:{latest_release['name']}")
            return

    print("No new release detected, exit")

if __name__ == "__main__":
    main()

