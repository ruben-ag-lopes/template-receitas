# Lançar localmente

## 1. Instalar as dependências (só da primeira vez)

```bash
python -m pip install -r requirements.txt
```

No Windows, instala também:

```bash
winget install --id tschoonj.GTKForWindows -e
winget install Gyan.FFmpeg
winget install UB-Mannheim.TesseractOCR
```

Os pacotes de idioma espanhol/português do Tesseract não vêm no instalador — ver
[TUTORIAL.md](TUTORIAL.md#1-pré-requisitos) se precisares deles (senão o OCR só lê inglês).

## 2. Lançar o servidor

A partir da raiz do projeto:

```bash
python -m src.web
```

Abre sozinho `http://127.0.0.1:5000` no browser. Para parar, `Ctrl+C` no terminal.

Se a porta 5000 já estiver ocupada, o arranque falha — fecha o que a está a usar, ou muda a
porta em `main()` no [src/web.py](src/web.py).
