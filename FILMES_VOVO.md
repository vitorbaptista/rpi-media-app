# 🎬 Filmes & Séries para a Vovó

Lista curada de conforto para tocar **um por dia** (ideia: botão **b6**).
Disponibilidade e áudio checados em páginas oficiais/Netflix BR em
**2026-06-22**; os itens já antigos também tinham validação ao vivo em
junho/2026. Catálogos mudam — reconfirme antes de fixar de vez.

## ✅ Status da execução (2026-06-14)

O handoff abaixo foi executado. Resumo do que ficou pronto e do que travou:

- **b6 agora é um rodízio multi-serviço** (`method = "playlist"`): escolhe **um
  título por dia** (rotação por dia-do-ano) e despacha para o serviço certo de
  cada item. Substituiu o `glob` antigo. É um botão de **conteúdo sob demanda
  (filmes/passeios), SEM canal ao vivo**. **6 itens, todos testados tocando na
  TV:**
  - `youtube` × 3 — Lisboa/Alfama, Funchal, Olhão (passeios de Portugal)
  - `netflix` × 3 — O Casamento de Romeu e Julieta (`70086050`), Meu Passado Me
    Condena (`80076609`), O Céu é de Verdade (`70295734`)
- **Netflix (TAREFA A):** ✅ **toca sozinho** pelo deep link atual — o medo de
  parar no título/seletor **não se confirmou**. `play_netflix` **não precisou de
  ajuste**.
- **Prime — Quando Chama o Coração (TAREFA B):** ❌ **fora do b6.** Na Prime BR
  o título é do **canal pago Lionsgate+** (selo/coroa dourada); não toca sem
  assinar esse add-on, então o `gti` não ajudaria. Reavaliar se assinar
  Lionsgate+ ou achar outra fonte dublada.
- **Globoplay (TAREFA C):** ✅ **Conta relogada** (ativada pelo celular) — o
  `globoplay:globo` ao vivo foi testado tocando ponta a ponta, **mas ficou de
  fora do b6 a pedido**: o b6 é um botão de **filmes/passeios**, e canal ao vivo
  toca a grade atual da Globo (imprevisível, inclui jornalismo). O relogin
  também deve ter **destravado o b4 (Canal Futura)**. Os VODs #8/#9 seguem fora
  (sem deep-link VOD no `play_globoplay`).
- **Deploy:** o `playlist` + a config foram implementados e testados **a partir
  da `luna` (máquina de dev)**, mas **não dá pra fazer deploy daqui** para o RPi
  de produção (`ssh rpi` falha na verificação de host key). **O deploy para o
  RPi (rsync + restart do `rpimedia.service`) fica com você.**
- **Como funciona o rodízio:** a ordem no `config.toml` não importa — o handler
  reordena com `sorted()` e indexa por dia-do-ano (mesma lógica do
  `play_sessao_da_tarde.py`), então a escolha do dia é determinística.
  `pytest`: 21 testes ✅; `pyright`: limpo; `code-reviewer`: limpo.

---

## 🧭 Regras de curadoria (o perfil dela)

Senhora de ~94 anos, brasileira, em depressão. O objetivo é **conforto**:
quente, esperançoso, baixa carga emocional, sempre com final feliz — clima de
**Sessão da Tarde**.

- ✅ Fé/inspiração ressoam (ela ama *The Chosen* — que **já está na programação**, então não repetimos aqui), mas **com variação**.
- ✅ Adora **Portugal**; e adora ser puxada para o **presente** (ela vive 100% em modo nostalgia, então conteúdo atual é um bônus).
- ✅ Luta/conflito leve tudo bem — **desde que não seja o centro** e resolva bem.
- ❌ Sem dramas, tristeza, tragédia, trauma, violência, terror. **Sem animação.**
- ❌ **Ela não gostou de *O Casamento de Romeu e Julieta***. Tratar como
  sinal contra comédia romântica barulhenta/centrada em rivalidade; não
  recolocar no b6 sem novo teste humano.
- ❌ **Ela não gostou de *O Céu é de Verdade***. Não gosta de filmes de alma
  (céu/quase-morte/além); evitar esse tema mesmo sob o rótulo de fé/inspiração.
- ✅ **Dublado em pt-BR** ou **nativo em português** (ela não lê legendas). Passeios visuais sem narração também valem.

Cada entrada traz onde assistir, IDs públicos (para ligar ao b6 depois) e o
estado do áudio. **Prime Video não expõe o `gti` publicamente** — esses
precisarão de uma consulta via ADB no Fire TV antes de virar botão.

---

## ▶️ No b6 agora

### 1. Maria, Mãe do Filho de Deus (2003) · *fé / família*
- **Onde:** Netflix (`netflix_id: 70196240`) — **português nativo**
- Um padre conta a história da Virgem Maria para uma menina enquanto ela espera
  a mãe voltar. Brasileiro, classificação livre, com Padre Marcelo Rossi.
- **Por quê:** fé familiar e tom mais caseiro; melhor aposta religiosa que
  produções bíblicas longas e violentas.

### 2. Tetra: Acreditar de Novo (2026) · *Brasil / presente / inspiração*
- **Onde:** Netflix (`netflix_id: 82032990`) — **português nativo**
- Documentário brasileiro sobre a Seleção de 1994, com entrevistas e imagens
  dos próprios jogadores.
- **Por quê:** atual, brasileiro, nostálgico sem ser triste; bom para puxar
  conversa com memórias boas.

### 3. The Middle · *família / sitcom*
- **Onde:** Netflix (`netflix_id: 70143859`) — **áudio em português**
- Frankie Heck e o marido Mike tentam equilibrar trabalho e casa enquanto criam
  três filhos no interior dos EUA.
- **Por quê:** sitcom familiar, honesta e agradável; deve ser um teste mais
  seguro que *Grace and Frankie* por não abrir com divórcio/sexualidade.

### 4. As Aventuras Escolhidas · *The Chosen / animação cristã*
- **Onde:** Netflix (`netflix_id: 82666465`) · Prime Video (`prime_video:
  0FJQKV6ZATP26APZZAXTFNH9IY`) — **áudio em português**
- Abby e Josué conhecem Jesus na antiga Galileia e aprendem sobre fé e amizade
  em episódios curtos.
- **Por quê:** deriva diretamente de *The Chosen*, tem classificação livre e
  formato curto. **Atenção:** é animação infantil; manter porque ela gosta de
  *The Chosen*, mas observar se o desenho a prende.

### 5. Davi: Nasce um Rei · *animação bíblica / musical*
- **Onde:** Netflix (`netflix_id: 82836255`) — **áudio em português**
- Jovem pastor destinado a se tornar rei enfrenta inimigos poderosos guiado
  pela fé.
- **Por quê:** fé, animação e música, com história bíblica conhecida. **Atenção:**
  tem conflito/Golias; observar se fica empolgante sem pesar.

### 6. Testamento: A História de Moisés · *documentário bíblico*
- **Onde:** Netflix (`netflix_id: 81341795`) — **áudio em português**
- Série documental em 3 episódios sobre Moisés como príncipe, profeta e líder.
- **Por quê:** tema bíblico conhecido e formato curto. **Atenção:** inclui
  escravidão, confronto com faraó e as pragas; pode ser mais pesado que
  *As Aventuras Escolhidas* e *Davi: Nasce um Rei*.

### 7. Noé · *épico bíblico*
- **Onde:** Netflix (`netflix_id: 70295061`) — **áudio em português**
- Noé recebe uma visão divina de uma inundação apocalíptica e constrói a arca.
- **Por quê:** história bíblica conhecida. **Atenção:** é drama épico 14 anos,
  com fim do mundo/conflito; testar em dias bons, não como conforto leve.

### 8. Um Pai em Apuros · *comédia brasileira / família*
- **Onde:** Netflix (`netflix_id: 82887570`) — **português nativo**
- Mãe cansada tira férias e deixa o marido cuidando das crianças, virando caos
  doméstico de comédia.
- **Por quê:** brasileiro, familiar e leve; bom contraponto aos títulos bíblicos.

---

## 🪑 Reserva (para variar a rotação)

Trocas fáceis quando quiser renovar — todos verificados disponíveis:

### Quando Chama o Coração (When Calls the Heart) · *série âncora*
- **Onde:** Prime Video BR — **dublado pt-BR** *(sem ID Netflix; `gti` via ADB depois)*
- Uma professora troca a cidade grande por um vilarejo de fronteira no início do século XX. Amizade, fé, comunidade e romance gentil, sempre com final reconfortante.
- **Por quê:** série Hallmark longa e aconchegante — perfeita para voltar um
  pouquinho a cada dia. *(Ainda depende de fonte tocável/assinatura.)*

### Meu Passado Me Condena: O Filme (2013) · *comédia brasileira*
- **Onde:** Netflix (`netflix_id: 80076609`) · Globoplay — **português nativo**
- Recém-casados embarcam num cruzeiro de lua de mel rumo à Europa e dão de cara com um ex e uma antiga paixão a bordo. Pura confusão e risada, final feliz.
- **Por quê:** comédia leve, ensolarada, sem peso — mas deixar em reserva por
  enquanto, porque a rejeição a *Romeu e Julieta* pode indicar saturação de
  comédia romântica/conjugal.

### Lisboa — Passeio por Alfama (4K) · *Portugal no presente*
- **Onde:** YouTube (`youtube_id: qVw_SkV797M`) — sem narração, **não precisa ler nada**
- Passeio tranquilo pelas ruelas, escadarias e azulejos do bairro mais antigo de Lisboa, em 4K, só com som ambiente.
- **Por quê:** Portugal de hoje, calmo e bonito — puxa ela para o presente sem nenhum drama.

### Funchal, Madeira (4K Walking Tour) · *Portugal no presente*
- **Onde:** YouTube (`youtube_id: z6qk4QcNnCg`) — sem narração
- Caminhada serena pela capital ensolarada da ilha da Madeira: flores, calçada portuguesa e o Atlântico ao fundo.
- **Por quê:** outra paisagem portuguesa (ilha), luminosa e relaxante.

### Olhão, Algarve (4K Walking Tour) · *Portugal no presente*
- **Onde:** YouTube (`youtube_id: lQxWeAZSHvs`) — sem narração
- Vila de pescadores no Algarve: mercado de peixe, orla da Ria Formosa e casario tradicional.
- **Por quê:** o charme do interior português, bem diferente das capitais — variedade de cenário.

---

## 💚 Vale a assinatura do Globoplay (sinalizados)

Você disse que pagaria o Globoplay se valesse a pena. **Estes três valem** — e
são os que mais "cara de casa" têm para ela:

### Chocolate com Pimenta (2003) · *novela de conforto / série âncora*
- **Onde:** Globoplay — **português nativo** ⚠️ *requer assinatura*
- Comédia romântica de época (anos 1920) de Walcyr Carrasco numa cidadezinha famosa por chocolates e doces. Leve, divertida, final feliz — são 209 capítulos, ótimo para o dia a dia.
- **Por quê:** novela brasileira gostosa e calorosa, exatamente o tom dela.

### Tá Escrito (2023) · *romance no presente*
- **Onde:** Globoplay — **português nativo** ⚠️ *requer assinatura*
- Alice (Larissa Manoela) ganha um caderno mágico em que tudo o que escreve para os signos vira realidade e vira sensação como astróloga. Comédia romântica atual e leve.
- **Por quê:** rom-com brasileira **do presente**, com atriz muito querida.

### É de Casa (ao vivo, Globo aos sábados) · *presente / acolhimento*
- **Onde:** Globoplay — canal **Globo ao vivo** (`globoplay: globo`) — **português nativo** ⚠️ *requer assinatura*
- Programa matinal de variedades com clima de casa: culinária, jardinagem, artesanato, música e conversas gentis.
- **Por quê:** conteúdo atual e caloroso que a traz para o hoje, sem peso. *(Único senão: tem alguns blocos jornalísticos leves.)*

---

## 🪑 Outras reservas pesquisadas

- **Sintra & Quinta da Regaleira (4K)** — YouTube `6kA6n9-5oJc` — jardins encantados de Sintra.
- **Lisboa 2025 (4K Walking Tour)** — YouTube `rAdDPOIzRlo` — Lisboa atual, bondinhos e praças.
- **Canal "Portugal Walking Tour"** — YouTube `aqevs6jLdJI` (e o canal `@portugalwalkingtour`) — fonte farta de novos passeios.
- **Ricos de Amor** — Netflix `81047512` — rom-com brasileira leve, mas deixar
  em reserva porque a rejeição a *Romeu e Julieta* pode ser rejeição ao gênero.
- **Um Natal Cheio de Graça** — Netflix `81443737` — comédia natalina brasileira;
  reservar para dezembro ou para teste manual, pois o humor pode ser espalhafatoso.
- **Evidências do Amor** — Netflix `82686555` — comédia romântica brasileira de
  2024; reservar, porque começa com abandono no altar.
- **A Vida de Jesus Cristo (filme completo dublado)** — YouTube `dfT8yHUyZWE` ou `YdK6g9gY028` — *opção bíblica, **sua decisão**: inclui a crucificação (como em The Chosen), pode ser bonita e familiar para ela ou pesada demais — avalie os primeiros minutos.*
- **Patrick: Aprendendo a Amar (2018)** — comédia britânica fofa com um pug; **fora do streaming BR hoje** — fique de olho se voltar.

---

## 🚫 Evitados de propósito (e por quê)

Para você entender a curadoria e não estranhar ausências óbvias:

- **Minha Mãe é uma Peça / Os Farofeiros / Loucas pra Casar** — comédias nacionais, mas humor pesado/adulto; *Loucas pra Casar* abre com tentativa de suicídio (grave dado a depressão dela).
- **O Casamento de Romeu e Julieta** — testado e rejeitado por ela; remover da
  rotação, apesar de ser leve no papel.
- **Mazzaropi / filmes centrados em Mazzaropi** — não adicionar por enquanto.
- **Fátima**, **Jesus** (novela Record), **A Bíblia**, **Fé Para o Impossível**, **Milagres do Paraíso**, **Eu Só Posso Imaginar** — fé que ela gosta, **mas** o núcleo é sofrimento/violência/doença/trauma. Pesados demais.
- **Glória** (Netflix Portugal) — é português, porém thriller de espionagem tenso da Guerra Fria.
- **Cantando na Chuva**, **A Noviça Rebelde**, **Sissi** — clássicos lindos, mas **sem disponibilidade dublada confirmada** no Brasil hoje (ou sem dublagem pt-BR).

---

## 🔌 Notas para ligar ao botão b6 (depois)

- O b6 deste worktree já é `method = "playlist"`: o controller escolhe um item
  por dia e despacha para o método real (`netflix`, `youtube`, etc.).
- Itens atuais do b6 em `config.toml`: `70196240`, `82032990`,
  `70143859`, `82666465`, `82836255`, `81341795`, `70295061`, `82887570`.
- Prime Video usa IDs de detalhe públicos quando disponíveis; ainda vale
  testar na TV porque alguns títulos podem exigir assinatura/canal add-on.
- Para incluir Globoplay VOD, ainda falta suporte a deep link de VOD; o método
  atual abre canal ao vivo por slug.

---

## 🤖 Próxima sessão — prompt para o Claude (rodar com a TV livre)

> ✅ **JÁ EXECUTADO em 2026-06-14** — ver "Status da execução" no topo. O bloco
> abaixo fica como registro. O que sobrou para uma próxima rodada: (a) **deploy
> para o RPi**; (b) decidir sobre o **Prime/Lionsgate+** para "Quando Chama o
> Coração"; (c) se quiser, adicionar suporte a **VOD do Globoplay** (#8/#9).
> *(Globoplay já foi relogado; `globoplay:globo` ao vivo foi testado mas ficou
> fora do b6 a pedido — b6 é só filmes/passeios, sem canal ao vivo.)*

> **Como usar:** abra uma sessão do Claude Code neste repo **com a TV do Fire TV
> (`192.168.15.174`) livre** e diga *"execute o handoff do FILMES_VOVO.md"*.
> O bloco abaixo é autossuficiente.

```
TAREFA: pegar os IDs que faltam, validar a reprodução em cada serviço e ligar o
botão b6 para tocar UM título por dia desta lista (FILMES_VOVO.md). Substitui o
b6 atual (method="glob" sobre arquivos locais).

PRÉ-CHECAGEM
- Confirmar com o usuário que a TV está LIVRE (vou assumir o controle dela).
- `adb connect 192.168.15.174` e confirmar em `adb devices`.
- Ler: rpimedia/devices.py (play_netflix / play_prime_video / play_globoplay),
  rpimedia/controller.py (_handle_method_call), play_sessao_da_tarde.py (rotação
  diária por dia-do-ano) e config.toml (bloco [remote.keys.b6]).
- Testar qualquer título com: `rpimedia send_event <method> <param>`
  (ex.: `rpimedia send_event youtube qVw_SkV797M`).

TAREFA A — Netflix (validar e endurecer)
- Atenção: play_netflix HOJE só dispara `netflix://title/<id>` e NÃO envia um
  "play" depois (diferente de play_prime_video, que manda DPAD_CENTER). Pode
  parar na página do título ou no seletor de perfil.
- Testar: `rpimedia send_event netflix 70086050` (O Casamento). Observar se
  toca sozinho, para no título, ou trava no seletor de perfil.
- Se não tocar: editar play_netflix p/ esperar ~NETFLIX_WAIT e enviar
  KEYCODE_DPAD_CENTER (espelhar play_prime_video); se travar no seletor de
  perfil, replicar o tap do play_globoplay. Re-testar até tocar de fato.

TAREFA B — Prime Video (pegar o gti)
- Candidatos de gti já extraídos das URLs /detail/ do Prime (TESTAR primeiro):
    Quando Chama o Coração  ->  0H6D8L0R8URHADZLGSY1KIB564
    (O Casamento, alt.)     ->  0LSDAKAM9M0TFCJWN499H62QEF
- Testar: `rpimedia send_event prime_video 0H6D8L0R8URHADZLGSY1KIB564`. Se abrir
  o título certo e tocar, anotar o gti confirmado aqui no arquivo.
- Se falhar: abrir o título manualmente no app Prime na TV e extrair o gti real
  com `adb shell dumpsys activity activities | grep -i gti` (ou inspecionar o
  intent atual). Atualizar este arquivo.

TAREFA C — Globoplay (CUIDADO com o gap)
- play_globoplay atual abre CANAL AO VIVO (`canais/<slug>`), NÃO títulos VOD.
    - "É de Casa" (#10) -> usar canal ao vivo `globo` (igual ao b4 com "futura").
      Lembrar: ao vivo mostra a GRADE ATUAL, então só é "É de Casa" sáb. de manhã;
      no resto do tempo é a programação corrente da Globo.
    - "Chocolate com Pimenta" (#8) e "Tá Escrito" (#9) são VOD -> SEM suporte hoje.
      Para incluir: adicionar um método novo de deep-link VOD do Globoplay
      (abrir `globoplay.globo.com/v/<id>/` ou a página da série e dar play).
      Senão, deixar os dois fora do b6 por enquanto.

TAREFA D — Ligar o b6 (rodízio multi-serviço, um por dia)
- Um botão liga a UM método; precisamos de despacho por título. Implementar um
  método novo (ex.: `playlist`) em controller.py que recebe uma lista de
  {method, param} e escolhe um item por dia (mesma lógica de dia-do-ano de
  play_sessao_da_tarde.py; ou aleatório), chamando o método certo de cada item.
- Itens iniciais do b6 (só os que comprovadamente TOCAM — atualizar após A/B/C):
    youtube      qVw_SkV797M   # Lisboa / Alfama
    youtube      z6qk4QcNnCg   # Funchal / Madeira
    youtube      lQxWeAZSHvs   # Olhão / Algarve
    netflix      70086050      # O Casamento de Romeu e Julieta   (após A)
    netflix      80076609      # Meu Passado Me Condena            (após A)
    netflix      70295734      # O Céu é de Verdade                (após A)
    prime_video  <gti>         # Quando Chama o Coração            (após B)
- Atualizar [remote.keys.b6] no config.toml e arquivar/remover o glob antigo.

TAREFA E — Fechamento
- Testar cada item do b6 ponta a ponta na TV e confirmar reprodução.
- Rodar o loop do code-reviewer (ver CLAUDE.md) nos arquivos alterados até limpar.
- Atualizar este arquivo: marcar cada título como ✅ tocando e registrar os gti's
  e ajustes descobertos.
- (Opcional) Se quiser tocar automático todo dia, adicionar uma linha no
  prod.crontab chamando o b6 (ex.: `rpimedia send_event keyboard_input d`),
  no estilo das outras entradas.
```
