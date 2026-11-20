import os
import sys

os.environ["PYTHONPATH"] = r"C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS"
os.environ["HF_HOME"] = r"C:\Users\devar\Desktop\MAYA AI PROJECT\MAYA AI\Model\hf"

from huggingface_hub import snapshot_download

path = snapshot_download(
    "minishlab/potion-multilingual-128M",
    local_dir=r"C:\Users\devar\Desktop\MAYA AI PROJECT\MAYA AI\Model\hf\hub\models--minishlab--potion-multilingual-128M",
)
print("Downloaded to:", path)
