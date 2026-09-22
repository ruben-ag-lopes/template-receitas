# Tutorial de Uso — Template Receitas

Gerador de PDFs de receitas a partir de ficheiros `.txt` simples, no formato de um caderno
de receitas de duas folhas A5.
Inclui uma interface web que extrai a receita diretamente de um link (reel do Instagram, TikTok,
YouTube) e gera o PDF automaticamente.

## 1. Pré-requisitos

Já instalados neste ambiente:

- Python 3.12
- `jinja2`, `weasyprint`, `pytest`, `flask`, `yt-dlp`, `numpy` (`requirements.txt`)
- GTK3 Runtime for Windows (necessário para o WeasyPrint gerar PDF)
- `ffmpeg` e Tesseract OCR (para ler o texto e tirar a fotografia do prato a partir do vídeo)
- Pacotes de idioma `spa` e `por` do Tesseract — a maioria das receitas não vem em inglês.
  O instalador do Tesseract só traz `eng`; os outros dois ficam numa pasta própria em
  `%LOCALAPPDATA%\Template_Receitas\tessdata\`, porque a pasta de instalação
  (`Program Files`) não é editável sem admin.

A base de dados (`recipes/receitas.db`) usa SQLite, que vem embutido no Python — não precisa de
nada extra. A tradução usa a API gratuita do MyMemory por HTTP simples — também sem
dependências novas.

Se preparares uma máquina nova, instala com:

```bash
python -m pip install -r requirements.txt
```

No Windows, instala também:

```bash
winget install --id tschoonj.GTKForWindows -e
winget install Gyan.FFmpeg
winget install UB-Mannheim.TesseractOCR
```

Os pacotes de idioma extra (`spa`, `por`) não vêm com o instalador; descarrega-os e copia-os
para a pasta própria:

```bash
curl -L -o spa.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/spa.traineddata
curl -L -o por.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata
# junta tambem o eng.traineddata que vem com a instalacao
copy "C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata" .
move *.traineddata "%LOCALAPPDATA%\Template_Receitas\tessdata\"
```

Sem o ffmpeg/Tesseract tudo o resto continua a funcionar — só deixa de se ler o texto e a foto
que só existem no vídeo (a página avisa quando isso falta). Sem os pacotes de idioma, o OCR só
lê inglês.

## 2. Schema da receita (.txt)

Os campos correspondem um a um ao template de caderno (duas folhas A5):

```
TITULO: Nome da receita              -> RECIPE
PORCOES: 4                            -> Serves
TEMPERATURA: 180 C                    -> Temp
TEMPO: 15 min                         -> Prep time
COZEDURA: 25 min                      -> Cook time
ORIGEM: @autor (instagram)            -> Recipe from
TAGS: sobremesa, gordice              -> caixa do curso + Notes
NOTAS: texto livre                    -> Notes
IMAGEM: recipes/images/receita.jpg    -> foto na folha das Directions
INGREDIENTES:                         -> Ingredients
- item 1
PASSOS:                               -> Directions
- passo 1
```

Regras:
- `TITULO`, `INGREDIENTES` e `PASSOS` são obrigatórios — os restantes campos são todos
  opcionais.
- Se `TITULO`, `INGREDIENTES` ou `PASSOS` faltarem, o parser recusa o ficheiro com uma
  mensagem clara em vez de gerar um PDF incompleto.
- Tudo o resto fica **em branco no PDF** quando a origem não o refere, com a linha
  desenhada para se escrever à mão — como no caderno impresso.
- `TAGS` são exatamente duas categorias fechadas (ver abaixo), atribuídas automaticamente.
- `IMAGEM` é o caminho para a fotografia do prato (relativo à raiz do projeto).

**Difficulty e Rating não têm campo no schema, de propósito**: são juízos de quem cozinha,
não dados do post. O PDF desenha as dez estrelas sempre vazias, para as marcares à mão
depois de fazeres a receita.

### As duas categorias

Cada receita leva sempre duas tags, escolhidas de vocabulários fechados:

| Tipo de prato | Característica distintiva |
| --- | --- |
| entrada, prato de carne, prato de peixe, sobremesa, doce, snack | sem glúten, sem lactose, ocasião especial, saudável, gordice, assado |

O **tipo de prato** marca uma das quatro caixas do template, e a **característica
distintiva** vai para o campo `Notes`:

| Tipo de prato | Caixa no template |
| --- | --- |
| entrada | Starter |
| prato de carne, prato de peixe | Main |
| snack | Side/Snack |
| sobremesa, doce | Dessert |

A característica só é "sem glúten" ou "sem lactose" quando o texto de origem o diz por
palavras (ex: "sem glúten", "vegano") — nunca se deduz da ausência de um ingrediente, porque
uma receita pode levar farinha sem a listar explicitamente.

Exemplo completo: [recipes/raw/sopa-de-tomate.txt](recipes/raw/sopa-de-tomate.txt)

## 3. Extrair uma receita a partir de um link (interface web)

### Lançar o servidor

A partir da raiz do projeto:

```bash
python -m src.web
```

Isto arranca o servidor em `http://127.0.0.1:5000` e abre-o sozinho no browser passado 1
segundo (`webbrowser.open`, em [src/web.py](src/web.py)). Para parar, `Ctrl+C` no terminal
onde correu.

Fica só acessível **nesta máquina** — `127.0.0.1` não é visível na rede. Se a porta 5000 já
estiver ocupada por outra coisa, o arranque falha com `OSError: [WinError 10048]`; ou fechas o
que está a usá-la, ou mudas a porta em `main()` no [src/web.py](src/web.py) (`host, port =
"127.0.0.1", 5000`).

### Usar

Abre `http://127.0.0.1:5000` no browser. Colas o link, carregas em **Extrair e gerar PDF** e,
se a receita estiver completa, o `.txt` é gravado, o PDF é gerado e a receita fica arquivada
na base de dados — tudo numa só ação, sem precisares de editar nada. A leitura do vídeo é a
parte mais lenta (dezenas de segundos a um minuto ou mais, conforme a duração) — é o preço de
ler as legendas com qualidade em vez de só o texto escrito no post.

### O que o sistema lê (numa só passagem)

| Fonte | Dá tipicamente |
| --- | --- |
| Legenda do post | ingredientes, por vezes passos e tempo |
| Primeiro comentário do post | a receita completa, quando a legenda é só um gancho |
| Texto sobreposto no vídeo (OCR) | os passos que a legenda não tem, incluindo legendas de uma palavra ("SÁCATELOS") |
| Fotograma do vídeo (ou capa do post) | a fotografia do prato final para o PDF |

Não lê áudio. Só o **primeiro** comentário do post é lido (não a lista toda) — é onde a
receita costuma estar quando o autor a escreve nos comentários em vez da legenda. Como a
receita tanto pode estar num sítio como noutro, cada fonte é pontuada (marcadores,
quantidades com unidades, verbos de cozinha — incluindo imperativos com pronome colado do
espanhol, "sácalo", "mézclalo" — e cabeçalhos como `INGREDIENTES:` ou `PREPARO:` em
português/espanhol/inglês) e os ingredientes podem vir de uma fonte e os passos de outra. O
painel lateral mostra **de onde veio cada campo** e o texto integral de cada fonte lida.

A fotografia do prato é escolhida automaticamente, e **nunca leva texto por cima**: só entram
fotogramas onde o OCR não detetou letra nenhuma, e entre esses escolhe-se o mais nítido da
segunda metade do vídeo (é aí que o prato pronto aparece). A capa do post, usada quando o
vídeo falha, passa pela mesma verificação — costuma trazer o título desenhado. Se o vídeo
tiver legenda do princípio ao fim, fica sem foto: mais vale nenhuma do que uma com letras
atravessadas.

### Qualidade do OCR

O texto sobreposto ao vídeo é lido duas vezes por fotograma — a imagem normal e uma máscara
que isola só os pixels quase brancos — porque uma legenda é texto sólido sobre um fundo
variado (a própria fotografia), e o OCR direto falha nesse contraste. Só entram no resultado
as palavras em que o próprio Tesseract diz ter confiança (≥75%); um fotograma sem legenda
nenhuma (a maioria) fica corretamente vazio, em vez de forçar uma leitura de ruído.

A mesma leitura serve dois fins com exigências opostas, por isso tem dois limiares: os
**passos** querem precisão (≥75%, senão entra ruído de textura), e a escolha da **foto** quer
sensibilidade (basta ≥30% de suspeita de letras para pôr o fotograma de lado). Sem essa
separação, um fotograma com legenda mal lida passava por limpo e ia parar ao PDF com texto
por cima.

O número de fotogramas escala com a duração do vídeo (cerca de um por segundo, até 36) em vez
de um número fixo — legendas de vídeo costumam mudar a cada 1-2 segundos, por vezes uma
palavra de cada vez ao ritmo da fala, e um número fixo de fotogramas deixava vídeos mais
longos com intervalos grandes de mais, perdendo trocas de legenda inteiras. A mesma palavra
lida com e sem acento em fotogramas diferentes (ex: "sacatelos" e "sácatelos") conta como uma
só, mantendo a leitura mais completa.

### Quando falta alguma coisa

O extrator não inventa nada. Se `TITULO`, `INGREDIENTES` ou `PASSOS` não estiverem em lado
nenhum (nem na legenda, nem nos comentários, nem no vídeo), o PDF **não** é gerado — o `.txt`
fica numa caixa editável com o que falta assinalado, para completares à mão e carregares outra
vez em **Guardar e gerar PDF**. `TEMPO` fica em branco sem impedir nada, porque é opcional.

### Traduzir a receita

Escolhe uma língua na lista ao lado da caixa e carrega em **Traduzir** — usa a API gratuita
do [MyMemory](https://mymemory.translated.net/) para traduzir o texto que está agora na caixa
(funciona mesmo com campos por preencher, antes ou depois de completares a receita).

Só o **conteúdo** muda: o `TITULO`, os `INGREDIENTES` e os `PASSOS`. Os nomes dos campos
(`TITULO:`, `INGREDIENTES:`...), o `TEMPO`, o `IMAGEM` e as `TAGS` ficam exatamente iguais —
são vocabulário fixo do schema e das categorias, traduzi-los quebraria o parser e a pesquisa
na base de dados.

A língua de origem deteta-se sozinha, linha a linha — exceto nas linhas de quantidade ("200 g
de lentejas"), que enganam a deteção automática por serem curtas e numéricas; nesses casos
reaproveita-se a língua já detetada numa linha normal.

### Processar uma lista de links

Para tratar várias receitas de uma vez, abre **"Processar uma lista de links"** na página:
cola os links (um por linha) ou carrega um ficheiro `.txt` com eles. Aceita até 50 de cada vez.

A fila corre em segundo plano, um link de cada vez — podes fechar a página e voltar mais
tarde; a tabela mostra o estado de cada um e atualiza-se sozinha de 10 em 10 segundos:

| Estado | O que aconteceu |
| --- | --- |
| **pronta** | receita completa: `.txt`, PDF e registo na base de dados já gerados |
| **incompleta** | faltou `TITULO`, `INGREDIENTES` ou `PASSOS` — o botão **Completar** abre o rascunho no editor, sem repetir a leitura do vídeo |
| **erro** | o link falhou (post privado, removido, bloqueado); os restantes continuam |

Um link que rebente não pára a fila. Só corre uma lista de cada vez — duas em simultâneo
disputariam o Tesseract e o ficheiro da base de dados.

## 4. Comandos do CLI

Todos os comandos correm a partir da raiz do projeto:

```bash
python -m src.cli <comando> [argumentos]
```

### `add` — interpretar um `.txt` e gerar o PDF

```bash
python -m src.cli add caminho/para/receita.txt --contact "teu@email.com"
```

O que acontece:
1. O `.txt` é interpretado e validado.
2. Uma cópia é guardada em `recipes/raw/<slug>.txt` (nome derivado do título).
3. O PDF final é gerado em `recipes/output/<slug>.pdf`.
4. A receita é arquivada em `recipes/receitas.db`.

`--contact` é opcional — texto que aparece no rodapé (ex: email ou site).

### `list` — listar receitas guardadas

```bash
python -m src.cli list
```

Mostra os slugs de todas as receitas em `recipes/raw/`.

### `regenerate` — regerar PDFs a partir dos `.txt` já guardados

Útil depois de editares o template ou uma receita diretamente em `recipes/raw/`.

```bash
python -m src.cli regenerate                 # regenera todas
python -m src.cli regenerate sopa-de-tomate   # regenera só uma (pelo slug)
```

### `print` — alternativa sem WeasyPrint

Gera um `.html` pronto a abrir no browser para exportar em PDF via `Ctrl+P` (caso o WeasyPrint não esteja disponível):

```bash
python -m src.cli print sopa-de-tomate
```

Gera `recipes/output/sopa-de-tomate.html`.

## 5. A base de dados

Todas as receitas guardadas (pela interface web ou pelo CLI) ficam arquivadas em
`recipes/receitas.db`, um único ficheiro SQLite. Cada linha guarda:

- o `.txt` completo e as duas categorias, em colunas próprias e pesquisáveis;
- a fotografia do prato, em `BLOB` (a mesma imagem que vai para o PDF);
- o texto de origem (legenda, comentários, texto do vídeo) e o link do post, para auditoria.

Os ficheiros em `recipes/raw/` e `recipes/output/` continuam a ser a fonte principal — a base
de dados é o arquivo pesquisável por cima deles (ex: "todos os snacks", "tudo o que é
assado"), e pode abrir-se em qualquer visualizador de SQLite.

Gravar a mesma receita outra vez (mesmo título) atualiza a linha existente sem apagar a
fotografia se a nova gravação não trouxer nenhuma.

## 6. Estrutura de pastas

```
Template_Receitas/
├── recipes/
│   ├── raw/           # .txt originais, guardados por slug
│   ├── output/         # PDFs (e HTMLs) gerados
│   ├── images/          # fotografias extraídas do vídeo
│   └── receitas.db      # arquivo SQLite (texto + imagem + categorias)
├── src/
│   ├── models.py            # Recipe (dataclass)
│   ├── recipe_parser.py     # txt_to_recipe()
│   ├── renderer.py          # Jinja2 + WeasyPrint (embebe a foto em base64)
│   ├── cli.py                # comandos add/list/regenerate/print
│   ├── database.py           # arquivo SQLite
│   ├── categories.py         # classificação nas duas categorias
│   ├── translator.py         # traducao do .txt (API gratuita MyMemory)
│   ├── batch.py              # fila de links em segundo plano
│   ├── link_ingest.py        # legenda + 1º comentario de um link (yt-dlp)
│   ├── recipe_extractor.py   # decide onde esta a receita e monta o .txt
│   ├── frames_ocr.py         # texto no video + fotografia do prato (ffmpeg + tesseract)
│   └── web.py                 # interface web (Flask)
├── templates/
│   ├── recipe.html   # template A4 minimalista
│   └── web.html       # pagina da interface
└── tests/
    ├── test_parser.py
    ├── test_extractor.py
    ├── test_categories.py
    ├── test_database.py
    ├── test_translator.py
    ├── test_batch.py
    └── test_template.py
```

## 7. Correr os testes

```bash
python -m pytest tests/ -q
```

## 8. Ajustar o design

O layout vive todo em [templates/recipe.html](templates/recipe.html) (CSS inline no `<style>`),
e reproduz o caderno em duas folhas A5:

- **Folha 1**: `RECIPE`, os campos (`Serves`, `Temp`, `Prep time`, `Cook time`,
  `Recipe from`), a caixa com `Difficulty`/`Rating`/cursos, `INGREDIENTS` em duas colunas com
  caixas de visto, e a faixa cinzenta `NOTES`.
- **Folha 2**: a fotografia do prato (meia página) e `DIRECTIONS`.

Pontos de edição mais comuns:

- Tamanho da folha: regra `@page` (`size: A5`).
- Altura da fotografia: regra `.photo` (`88mm`, meia folha).
- Número de linhas em branco: `INGREDIENT_ROWS` e `DIRECTION_ROWS` em
  [src/renderer.py](src/renderer.py).
- Caixas de visto: regra `.check` — ficam fora do flexbox de propósito, senão o WeasyPrint
  corta-lhes os lados de baixo e da direita.

Depois de editar o template, corre `python -m src.cli regenerate` para atualizar todos os PDFs já gerados.

## 9. Fluxo típico do dia-a-dia

**A partir de um link:**

1. `python -m src.web` e cola o link do reel.
2. Se a receita sair completa, o PDF já está pronto — não é preciso fazer mais nada.
3. Se faltar `TITULO`, `INGREDIENTES` ou `PASSOS`, completa-os na caixa e carrega outra vez
   em **Guardar e gerar PDF**.

**A partir de vários links:**

1. `python -m src.web`, abre **"Processar uma lista de links"** e cola a lista (ou carrega
   um `.txt`).
2. Deixa correr — cada link demora um a dois minutos e a página vai-se atualizando.
3. No fim, trata só das que ficaram marcadas como **incompleta**, pelo botão **Completar**.

**A partir de um `.txt` escrito à mão:**

1. Escreve a receita num `.txt` (usa o exemplo como base).
2. `python -m src.cli add minha-receita.txt --contact "teu@email.com"`
3. Abre o PDF em `recipes/output/`.
4. Se quiseres corrigir algo, edita `recipes/raw/<slug>.txt` diretamente e corre `python -m src.cli regenerate <slug>`.

## 10. Plano de deploy na nuvem (ainda por implementar)

**Este capítulo é só o plano.** Nada aqui foi implementado — é para pedires a implementação
quando quiseres, sem teres de voltar a discutir a arquitetura.

### O problema de base: esta app não é "serverless-friendly"

GitHub + Vercel + Supabase é a stack certa para um site normal, mas esta app tem quatro
partes que não se dão bem com o modelo do Vercel (funções que arrancam por pedido, correm
por segundos, e não guardam nada em disco entre pedidos):

| Parte da app | Porque não cabe num Vercel serverless "tal como está" |
| --- | --- |
| Leitura do vídeo ([frames_ocr.py](src/frames_ocr.py)) | Descarrega o vídeo com `yt-dlp` e corre `ffmpeg`/`Tesseract` — binários nativos que não vêm no runtime Python do Vercel, e a leitura já demora 60-150s por link; o limite de execução do Vercel é 10s no plano gratuito (60s no Pro) |
| Geração do PDF ([renderer.py](src/renderer.py)) | O WeasyPrint precisa do Pango/Cairo/GDK-Pixbuf (a pilha toda do GTK3) — instalar isto num ambiente serverless é frágil e mal documentado |
| Fila de links em segundo plano ([batch.py](src/batch.py)) | Usa uma `threading.Thread` e estado em memória Python partilhado entre pedidos HTTP — no Vercel cada pedido pode cair numa instância diferente, e o processo não continua a correr depois de responder |
| Ficheiros gerados (`recipes/raw/`, `recipes/output/`, `recipes/images/`, `recipes/receitas.db`) | O disco do Vercel é só de leitura (exceto `/tmp`, que é apagado entre pedidos) — nada disto sobrevive de um pedido para o outro |

Nenhum destes quatro pontos é um "detalhe de configuração" — são incompatibilidades de
arquitetura. Portar isto a sério significa trocar OCR local por uma API de OCR na nuvem,
trocar o WeasyPrint por um serviço de HTML-para-PDF, e trocar a fila em memória por uma fila
a sério (job por job, numa tabela, com retries). É uma reescrita, não um deploy.

### A minha recomendação

**Não vale a pena para uma ferramenta pessoal**, a não ser que precises mesmo de lhe aceder
de fora desta máquina (telemóvel, outro computador, partilhar com alguém). Se for só para ti,
neste PC, ficar local com SQLite é estritamente melhor: sem custos, sem limites de tempo de
execução, sem reescrever OCR/PDF/fila, e sem depender da internet para gerar uma receita.

Se precisares mesmo de acesso remoto, a opção B abaixo (híbrida) dá isso sem reescrever a
parte pesada. A opção C (tudo serverless) só compensa se a lista de links crescer muito e
quiseres processar várias em paralelo na nuvem em vez de na tua máquina.

### Opção A — Manter local (SQLite), sem alterações

O que já está feito. `recipes/receitas.db` fica no disco desta máquina, os PDFs ficam em
`recipes/output/`. Continua a ser a opção recomendada enquanto for só para uso pessoal.

### Opção B — Híbrida: mantém o processamento local, publica só a leitura

A ideia: o que é pesado (ler o link, OCR, gerar PDF, a fila) continua a correr **aqui**, tal
como está. Só o que é "consultar o que já existe" passa a viver na nuvem, acessível de
qualquer lado.

1. **Supabase** — criar um projeto, migrar o schema de `database.py` (tabela `recipes`) para
   Postgres, e um bucket de Storage para as fotos e os PDFs (em vez de `recipes/images/` e
   `recipes/output/` locais).
2. **`src/database.py`** passa a escrever nos dois sítios: continua a gravar o SQLite local
   (para o CLI e o `python -m src.web` locais não pararem de funcionar) e, depois de cada
   receita ficar completa, envia uma cópia para o Supabase (título, ingredientes, passos,
   categorias, e a foto/PDF para o Storage).
3. **Vercel** aloja só uma página de consulta (lista/pesquisa de receitas, ver o PDF, ver a
   foto) que lê diretamente do Supabase — sem WeasyPrint, sem OCR, sem fila: só leitura de
   dados já prontos. Pode ser uma rota Flask nova e pequena, ou uma página estática com o
   cliente JS do Supabase.
4. **GitHub** guarda o código e liga-se ao Vercel para deploy automático a cada push (só da
   parte da página de consulta — o resto continua a correr só localmente, nunca no Vercel).

Resultado: continuas a extrair receitas aqui (rápido, sem custos, sem limites), e ganhas uma
página só de leitura acessível de fora. Não resolve processar links a partir do telemóvel.

### Opção C — Tudo na nuvem (reescrita a sério)

Só se um dia precisares de processar links sem estar a correr nada localmente. Troca:

- **OCR + foto do vídeo**: `yt-dlp`+`ffmpeg`+`Tesseract` locais → uma API de OCR na nuvem
  (ex: Google Cloud Vision) chamada a partir de uma Supabase Edge Function; o download do
  vídeo teria de correr nessa função também, o que traz os mesmos limites de tempo de
  execução do lado do Supabase.
- **Geração do PDF**: WeasyPrint local → um serviço de HTML-para-PDF externo, chamado por
  HTTP a partir de uma função serverless.
- **Fila** ([batch.py](src/batch.py)): thread em memória → uma tabela `jobs` no Supabase
  (Postgres) processada por um Cron do Vercel ou uma Edge Function do Supabase, um link de
  cada vez, com estado gravado na base de dados em vez de num objeto Python.
- **Base de dados e ficheiros**: SQLite local + `recipes/` → Supabase Postgres + Supabase
  Storage, como na opção B.
- **GitHub + Vercel**: o repositório liga-se ao Vercel para deploy automático; as variáveis de
  ligação ao Supabase (URL, chave) ficam nas *Environment Variables* do projeto Vercel.

Isto é bastante mais trabalho do que as outras opções, tem custos a partir de um certo volume
(minutos de função, armazenamento, chamadas à API de OCR), e troca "grátis e sem limites" por
"na nuvem e com limites de plano" — o oposto do que pediste no início deste projeto. Só faz
sentido se o acesso remoto passar a ser mesmo indispensável.
