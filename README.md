# 📺 RPI Media App

Sistema de automação de mídia para Raspberry Pi que controla um Chromecast ou um Fire TV via controle remoto IR ou teclado. Perfeito para criar uma experiência de TV automatizada para idosos ou qualquer pessoa que queira simplificar o acesso a conteúdo de vídeo.

## ✨ Funcionalidades

- **Controle por botões físicos** - Associe teclas do teclado ou controle IR a ações específicas
- **Reprodução de YouTube** - Toque vídeos do YouTube diretamente no Chromecast
- **Vídeos locais** - Reproduza arquivos MP4/MKV armazenados no Raspberry Pi
- **Controle de volume** - Aumente ou diminua o volume via comandos
- **Playlists automáticas** - Configure listas de vídeos que tocam em ordem aleatória
- **Automação por horário** - Use crontab para tocar conteúdo em horários específicos
- **Silêncio noturno** - Mute automático durante a madrugada para não atrapalhar o sono

## 🏗️ Arquitetura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Controle IR /  │────▶│   RPI Media     │────▶│   Chromecast    │
│    Teclado      │     │    (Python)     │     │      (TV)       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │   config.toml   │
                        │  (mapeamento)   │
                        └─────────────────┘
```

## 📋 Pré-requisitos

- Raspberry Pi (testado no Pi 4)
- Chromecast **ou** Fire TV na mesma rede
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (gerenciador de pacotes Python)
- Para Fire TV: pacotes de sistema `android-tools` (adb) e `avahi-utils` (avahi-browse), e ADB debugging habilitado no Fire TV (ver [FIRETV.md](FIRETV.md))
- Opcional: Receptor IR + controle remoto

## 🚀 Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/vitorbaptista/rpi-media-app.git
cd rpi-media-app
```

### 2. Instale as dependências

```bash
make install
```

### 3. Escolha o dispositivo (opcional)

Por padrão, o app controla um Chromecast. Para usar um Fire TV, adicione ao `config.toml`:

```toml
[device]
type = "firetv"                        # "chromecast" (padrão) ou "firetv"
# address = "192.168.15.174"           # opcional; se omitido, descobre via mDNS
```

### 4. Configure o mapeamento de teclas

Edite o arquivo `config.toml` para mapear teclas aos comandos desejados:

```toml
[remote.bindings]
3 = "volume_up"      # Tecla '3' aumenta volume
1 = "volume_down"    # Tecla '1' diminui volume
c = "b1"             # Tecla 'c' aciona o botão 1
f = "b2"             # Tecla 'f' aciona o botão 2
# ...

[remote.keys.volume_up]
method = "volume_up"
params = "15"        # Aumenta 15 unidades

[remote.keys.b1]
method = "youtube"
params = ["4CAmwaFJo6k"]  # ID do vídeo do YouTube

[remote.keys.b2]
method = "youtube"
params = [
    "zlin28kYqVI",  # Primeiro vídeo
    "AOrbv6bVqU4",  # Segundo vídeo (enfileirado)
]
```

### 5. Configure como serviço (produção)

```bash
sudo make setup
```

Isso irá:
- Instalar o serviço systemd
- Configurar o crontab com as automações

## 🎮 Uso

### Iniciar manualmente

```bash
uv run rpimedia start
```

### Enviar comando via terminal

```bash
# Simula pressionar a tecla 'c' (TV Aparecida)
uv run rpimedia send_event keyboard_input c

# Tocar um vídeo específico do YouTube
uv run rpimedia send_event youtube VIDEOID

# Ajustar volume
uv run rpimedia send_event volume_up 15
```

### Ver logs do serviço

```bash
make tail_logs
# ou
journalctl -u rpimedia.service -f
```

## ⏰ Automações (Crontab)

O arquivo `prod.crontab` configura as seguintes automações:

| Horário | Ação |
|---------|------|
| A cada 3 min | Verifica se algo está tocando; se não, liga TV Aparecida |
| 02h-07h (cada 3 min) | Muta o volume (silêncio noturno) |
| 10h e 16h | Toca "Sessão da Tarde" (filmes locais) |
| 11h e 18h | Toca playlist de música |
| 15h | Toca documentários sobre o Brasil |

Para aplicar o crontab:

```bash
make setup_crontab
```

## 📁 Estrutura do Projeto

```
rpi-media-app/
├── config.toml              # Configuração de teclas e playlists
├── rpimedia/                # Código principal
│   ├── cli.py              # Interface de linha de comando
│   ├── controller.py       # Controlador do Chromecast
│   ├── event_bus.py        # Sistema de eventos
│   ├── input_listener.py   # Escuta eventos de teclado
│   └── ipc_listener.py     # Comunicação entre processos
├── chromecast_checker.py    # Verifica se algo está tocando
├── mute_before_dawn.py      # Silencia durante a madrugada
├── play_sessao_da_tarde.py  # Toca filmes locais
├── get_current_media_info.py # Info do que está tocando
├── data/                    # Vídeos locais
│   └── sessao_da_tarde/
│       ├── chosen/         # Filmes selecionados
│       └── filmes/         # Todos os filmes
├── prod.crontab             # Configuração do cron
├── rpimedia.service         # Serviço systemd
└── Makefile                 # Comandos úteis
```

## 🎬 Métodos Disponíveis

| Método | Descrição | Parâmetros | Chromecast | Fire TV |
|--------|-----------|------------|:---:|:---:|
| `youtube` | Toca vídeo(s) do YouTube | Lista de IDs (11 chars) | ✅ | ✅ (sem enqueue) |
| `prime_video` | Toca título do Prime Video | GTI (`amzn1.dv.gti.<uuid>`) | ❌ | ✅ |
| `netflix` | Toca título do Netflix | ID numérico | ❌ | ✅ |
| `globoplay` | Abre o hub do canal no Globoplay | Slug do canal: `globo` ou `futura` (1) | ❌ | ✅ (2) |
| `video` | Toca um vídeo local | Caminho do arquivo | ✅ | ❌ |
| `glob` | Toca vídeo aleatório de um padrão | Padrão glob (ex: `data/**/*.mp4`) | ✅ | ❌ |
| `url` | Toca qualquer URL | URL completa | ✅ | ❌ |
| `volume_up` | Aumenta volume | Quantidade | ✅ | ✅ |
| `volume_down` | Diminui volume | Quantidade | ✅ | ✅ |
| `pause` | Pausa/retoma reprodução | - | ✅ | ✅ |

(1) Outros slugs (`globonews`, `gnt`, `multishow`, `sportv`, etc.) só funcionam com assinatura paga.

(2) `globoplay` para na página do canal — o fluxo gratuito não expõe um deep link para reprodução ao vivo, então o telespectador pressiona OK no controle para entrar.

Métodos incompatíveis com o dispositivo escolhido são rejeitados na inicialização do serviço com uma mensagem clara. Para detalhes do Fire TV (incluindo como obter GTIs do Prime Video), veja [FIRETV.md](FIRETV.md).

## 🔧 Deploy

Para enviar alterações para o Raspberry Pi:

```bash
make deploy
```

> **Nota:** Configure o host `rpi` no seu `~/.ssh/config` primeiro.

## 🐛 Solução de Problemas

### O Chromecast não é encontrado

- Verifique se o Raspberry Pi e o Chromecast estão na mesma rede
- Tente `catt scan` para listar dispositivos disponíveis

### Comandos não funcionam

- Verifique se o serviço está rodando: `systemctl status rpimedia.service`
- Veja os logs: `make tail_logs`

### Vídeos locais não tocam

- Certifique-se de que os arquivos estão em `data/sessao_da_tarde/`
- Verifique as permissões dos arquivos

## 📝 Licença

MIT

## 🙏 Créditos

- [catt](https://github.com/skorokithakis/catt) - Cast All The Things (controle do Chromecast)
- [uv](https://github.com/astral-sh/uv) - Gerenciador de pacotes Python ultrarrápido
