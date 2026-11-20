$env:PYTHONPATH = "C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS"
$env:HF_HOME = "C:\Users\devar\Desktop\MAYA AI PROJECT\MAYA AI\Model\hf"
python -c "
from huggingface_hub import snapshot_download
path = r'C:\Users\devar\Desktop\MAYA AI PROJECT\MAYA AI\Model\hf\hub\models--minishlab--potion-multilingual-128M'
result = snapshot_download('minishlab/potion-multilingual-128M', local_dir=path)
print('DOWNLOAD_DONE:', result)
" > C:\Users\devar\Desktop\MAYA AI PROJECT\download_output.txt 2>&1
