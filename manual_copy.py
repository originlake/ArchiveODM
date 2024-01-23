import os
from archive import copy_images

if __name__ == "__main__":
    copy_images(os.environ["SOURCE_IMAGE"], os.environ["TARGET_IMAGE"])