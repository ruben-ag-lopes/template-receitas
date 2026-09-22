# Template Receitas

Gerador de PDFs de receitas num template de caderno (duas folhas A5), com uma interface web
que extrai a receita diretamente de um link (reel do Instagram, TikTok, YouTube) — legenda,
comentários e vídeo — e gera o PDF automaticamente.

Ver [TUTORIAL.md](TUTORIAL.md) para o guia completo: pré-requisitos, o schema do `.txt`,
como correr a interface web e o CLI, a base de dados, os testes, e o plano de deploy.

## Arranque rápido

```bash
python -m pip install -r requirements.txt
python -m src.web
```

Abre `http://127.0.0.1:5000`, cola um link e carrega em **Extrair e gerar PDF**.
