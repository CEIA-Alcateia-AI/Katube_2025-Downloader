# Configuração Rápida - KATUBE 2025

Guia simplificado para configurar o projeto em poucos minutos.


### 1. **Clone e Prepare**
```bash
git clone https://github.com/SEU_USUARIO/katube-2025-downloader.git
cd katube-2025-downloader
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/Mac  
source venv/bin/activate

pip install -r requirements.txt
```

### 2. **Configure Básico (Apenas Downloads Locais)**
```bash
# Copie o template
cp env.example .env

# Edite apenas se quiser mudar o diretório de download
# Deixe o resto como está para funcionar localmente
```

### 3. **Teste Rápido**
```bash
python app.py
```
Acesse: `http://localhost:5000`

**Pronto! Já funciona para downloads locais.**

---

## Configuração GCP (Opcional - +5 minutos)

### **Opção A: Arquivo de Credenciais (Mais Fácil)**
1. No [Google Cloud Console](https://console.cloud.google.com/):
   - Vá em "IAM & Admin" > "Service Accounts"
   - Crie uma conta de serviço
   - Baixe o arquivo JSON
2. Renomeie para `gcp_credentials.json` e coloque na raiz do projeto
3. Edite `.env`:
   ```bash
   GCP_PROJECT_ID=seu_projeto_id_aqui
   GCP_BUCKET_NAME=seu_bucket_aqui
   ```

### **Opção B: Google Cloud SDK**
```bash
# Instale o gcloud CLI primeiro
gcloud auth login
gcloud config set project SEU_PROJETO_ID
gcloud auth application-default login
```

---

## YouTube API (Opcional - Para Canais)

1. Vá em [Google Developers Console](https://console.developers.google.com/)
2. Ative "YouTube Data API v3"
3. Crie uma API Key
4. Adicione no `.env`:
   ```bash
   YOUTUBE_API_KEY=sua_api_key_aqui
   ```

---

## Configurações Comuns

### **Mudar Diretório de Download**
```bash
# No .env
AUDIOS_BAIXADOS_DIR=C:\MeusDownloads\YouTube
```

### **Ajustar Qualidade de Áudio**
```bash
# No .env
AUDIO_FORMAT=flac    # ou wav, mp3
SAMPLE_RATE=24000    # ou 16000, 44100, 48000
```

### **Limitar Downloads por Canal**
```bash
# No .env
MAX_VIDEOS_PER_CHANNEL=2500
```

---

## Problemas Comuns

### **"ModuleNotFoundError"**
```bash
# Certifique-se que o ambiente virtual está ativo
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate

pip install -r requirements.txt
```

### **"Permission denied" (GCP)**
- Verifique se a conta de serviço tem permissão "Storage Object Admin"
- Confirme se o bucket existe

### **Downloads lentos**
- Normal para vídeos longos
- Verifique sua conexão de internet

---

## Checklist de Funcionamento

- [ ] Python 3.8+ instalado
- [ ] Ambiente virtual ativo
- [ ] Dependências instaladas (`pip list` mostra flask, yt-dlp, etc.)
- [ ] Arquivo `.env` criado e configurado
- [ ] `python app.py` executa sem erros
- [ ] Interface abre em `http://localhost:5000`
- [ ] Consegue baixar um vídeo de teste

### **Para GCP (Opcional):**
- [ ] Credenciais GCP configuradas
- [ ] Projeto e bucket existem
- [ ] Permissões corretas configuradas

---

## Pronto para Usar!

**Downloads Locais**: Funciona imediatamente após instalação básica
**Upload GCP**: Requer configuração adicional de credenciais
**Canais Completos**: Requer YouTube API Key

**Teste com um vídeo curto primeiro!**
