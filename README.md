# YouTube Audio Downloader

Pipeline simplificada para download de áudios do YouTube e upload automático para Google Cloud Storage.

## 🚀 Funcionalidades

- **Download de Vídeos**: Baixa áudios individuais em FLAC 24kHz
- **Download de Canais**: Escaneia e baixa todos os vídeos de um canal
- **Upload Automático**: Envia arquivos para bucket GCP automaticamente
- **Metadata Completa**: Gera arquivos JSON com informações dos vídeos
- **Interface Web**: Interface simples e intuitiva
- **Organização por Sessão**: Cada download é organizado em sessões separadas

## 📋 Requisitos

- Python 3.8+
- Conta Google Cloud com bucket configurado
- YouTube Data API key (opcional, para canais)

## 🛠️ Instalação

1. **Clone o repositório**:
```bash
git clone <repository-url>
cd katube-2025-downloader
```

2. **Crie um ambiente virtual**:
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# ou
source venv/bin/activate  # Linux/Mac
```

3. **Instale as dependências**:
```bash
pip install -r requirements.txt
```

4. **Configure o Google Cloud SDK**:
   
   **Opção 1 - Configuração Automática:**
   ```bash
   # Instale o Google Cloud SDK
   # Windows: https://cloud.google.com/sdk/docs/install
   # Linux/Mac: curl https://sdk.cloud.google.com | bash
   
   # Configure
   gcloud init
   gcloud auth login
   gcloud config set project SEU_PROJETO_ID
   gcloud auth application-default login
   ```
   
   **Opção 2 - Arquivo de Credenciais:**
   - Baixe o arquivo JSON de credenciais do GCP
   - Renomeie para `gcp_credentials.json`
   - Coloque na raiz do projeto
   
   **Manual:**
   - Veja o arquivo `setup_gcp.md` para instruções detalhadas

5. **Configure a YouTube API** (opcional, para canais):
   - Crie um arquivo `.env` na raiz do projeto:
   ```
   YOUTUBE_API_KEY=sua_api_key_aqui
   ```

6. **Configure variáveis de ambiente**:
   ```bash
   # Copie o template
   cp env.example .env
   
   # Edite com suas configurações
   # Windows: notepad .env
   # Linux/Mac: nano .env
   ```

## 🎯 Uso

1. **Inicie a aplicação**:
```bash
python app.py
```

2. **Acesse a interface web**:
```
http://localhost:5000
```

3. **Faça downloads**:
   - **Vídeo individual**: Cole a URL do vídeo
   - **Canal completo**: Cole a URL do canal (requer YouTube API key)

## 📁 Estrutura de Saída

### Local
```
audios_baixados/output/
├── download_session_20241201_143022/
│   ├── downloads/
│   │   ├── video1.flac
│   │   └── video2.flac
│   ├── metadata/
│   │   ├── video1_metadata.json
│   │   └── channel_summary.json
│   ├── video_urls.txt
│   └── download_results.json
```

### Google Cloud Storage
```
gs://dataset_youtube_katube/
└── youtube_downloads/
    ├── download_session_20241201_143022/
    │   ├── downloads/
    │   ├── metadata/
    │   ├── video_urls.txt
    │   ├── download_results.json
    │   └── upload_summary.json
```

## ⚙️ Configuração

### Variáveis de Ambiente (.env)
```bash
# YouTube API (opcional, para canais)
YOUTUBE_API_KEY=sua_youtube_api_key

# Diretório de saída (opcional)
AUDIOS_BAIXADOS_DIR=C:\caminho\para\audios

# Formato de áudio (opcional)
AUDIO_FORMAT=flac
SAMPLE_RATE=24000
```

### Credenciais GCP
- Arquivo: `gcp_credentials.json`
- Ou variável: `GOOGLE_APPLICATION_CREDENTIALS`
- Permissões necessárias: `Storage Object Admin`

## 🔧 Dependências Principais

- **Flask**: Interface web
- **yt-dlp**: Download do YouTube
- **google-cloud-storage**: Upload para GCP
- **google-api-python-client**: YouTube Data API

## 📊 Saídas Geradas

1. **Áudios FLAC**: Arquivos de áudio em alta qualidade
2. **Metadata JSON**: Informações detalhadas dos vídeos
3. **Lista de URLs**: Arquivo .txt com todas as URLs processadas
4. **Resumos**: Arquivos JSON com estatísticas da sessão
5. **Upload Summary**: Relatório do upload para GCP

## 🚨 Troubleshooting

### "GCP uploader not available"
- Instale: `pip install google-cloud-storage`
- Configure credenciais GCP

### "YouTube API key not available"
- Configure `YOUTUBE_API_KEY` no arquivo `.env`
- Necessário apenas para escaneamento de canais

### Erro de permissões GCP
- Verifique se a conta de serviço tem permissão `Storage Object Admin`
- Confirme se o bucket existe e está acessível

## 📝 Licença

Este projeto é fornecido como está, para uso educacional e pessoal.
