import yaml
import requests
import docker

client = docker.from_env()

with open('config.yml', 'r') as fhand:
    config = yaml.safe_load(fhand)

def pull_and_push(tag_name):
    latest = client.images.pull(config['odm_registry'], tag='latest')
    gpu_latest = client.images.pull(config['odm_registry'], tag='gpu')
    latest.tag(config['archive_registry'], tag=tag_name)
    gpu_latest.tag(config['archive_registry'], tag='gpu_'+tag_name)
    client.images.push(config['archive_registry'], tag=tag_name)
    client.images.push(config['archive_registry'], tag='gpu_'+tag_name)

def main():
    resp = requests.get(f"https://registry.hub.docker.com/v2/repositories/{config['archive_registry']}/tags", timeout=30)
    assert resp.ok, "Can't get list of archived tags"
    archieved_tags = [x['name'] for x in resp.json()['results']]   
    resp = requests.get(f"https://api.github.com/repos/{config['odm_repository']}/releases/latest")
    assert resp.ok, "Can't get latest release"
    latest_release = resp.json()
    if latest_release['name'] not in archieved_tags:
        pull_and_push(latest_release['name'])
    else:
        print("Already archived latest release")

if __name__ == "__main__":
    main()
    
