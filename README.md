# Assistente RAG — Disruptive Architectures

Chat em português para estudar os conteúdos públicos de Inteligência Artificial da disciplina [Disruptive Architectures](https://arnaldojr.github.io/DisruptiveArchitectures/). A aplicação recupera trechos do site, pede ao Gemini uma resposta fundamentada e mostra links das páginas usadas.

## Arquitetura

1. No build, `app.ingest` lê o sitemap oficial, seleciona somente as páginas em `/aulas/IA/` e `/aulas/genAI/`, extrai o conteúdo principal e grava trechos com título, seção e URL em `data/corpus.json`.
2. O modelo `gemini-embedding-2` gera `data/index.json`. O índice fica no artefato da aplicação; não há banco vetorial ou coleta a cada pergunta.
3. `POST /api/chat` gera o embedding da pergunta, recupera até seis trechos e usa `gemini-3.5-flash-lite` para escrever uma resposta estruturada. A API valida os números das fontes antes de retornar os links.
4. O navegador guarda somente a conversa da aba em `sessionStorage` e envia as últimas mensagens a cada pergunta. Uma nova conversa apaga esses dados da aba.

A base inclui IA tradicional, IA generativa, seus laboratórios e avaliações publicadas nessas duas seções. Conteúdos de IoT, agenda e checkpoints fora dessas seções não são indexados. O diretório `data/` é gerado localmente e não deve ser enviado ao GitHub. Cada novo build coleta o conteúdo público vigente e recria os embeddings. O texto da base é conteúdo de terceiros: mantenha os links das fontes na interface.

## Executar localmente

Requer Python 3.12 e uma chave da Gemini API configurada na variável de ambiente `GEMINI_API_KEY`. Configure a chave temporariamente no terminal ou no gerenciador de segredos; não a salve neste repositório. A chave é usada apenas no servidor.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.ingest
.venv/bin/uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8000/`. Para refazer somente os embeddings de um corpus já coletado, execute `.venv/bin/python -m app.ingest --embed-only`.

### Interface da API

`POST /api/chat` aceita JSON:

```json
{
  "message": "O que é RAG?",
  "conversation_id": null,
  "history": []
}
```

O retorno contém `conversation_id`, `status` (`answered`, `clarify` ou `insufficient`), `answer` e `sources` com `number`, `title`, `section` e `url`. O histórico é uma lista opcional de objetos `{ "role": "user|assistant", "content": "..." }`, limitada a 12 mensagens. `GET /api/health` informa se o índice está pronto e quantas páginas e trechos foram carregados.

## Avaliar respostas

Com a chave e o índice configurados, execute:

```bash
.venv/bin/python -m scripts.evaluate
```

O roteiro faz perguntas reais sobre RAG e aprendizado de máquina, além de casos sem resposta na base e pergunta vaga. Ele confere status e páginas citadas, imprimindo as respostas para revisão humana. Para avaliar a qualidade, confirme também que **cada afirmação** é sustentada pelas fontes exibidas; um link correto sozinho não prova a resposta.

## Publicar no Render

1. Crie um repositório GitHub vazio em sua conta. Para evitar o diretório `.git` provisório deste ambiente, extraia `IARAG-deploy.zip` em uma pasta nova e envie **o conteúdo extraído** para o repositório. O ZIP contém apenas código e configuração, sem chave nem dados gerados.
2. No Render, use **New → Blueprint** e selecione esse repositório. O arquivo `render.yaml` define um Web Service Python no plano gratuito.
3. Na criação do Blueprint, informe `GEMINI_API_KEY` como segredo quando o Render solicitar. O build instala dependências, coleta o site público e cria o índice vetorial.
4. Aguarde o build e confira `https://<servico>.onrender.com/api/health`. O retorno deve ter `status: "ok"` e a contagem da base. Abra a URL raiz e faça uma pergunta com fontes.

Se preferir Git no terminal, depois de extrair o ZIP em uma pasta nova, execute `git init`, `git add .`, `git commit -m "feat: cria assistente RAG da disciplina"`, `git branch -M main`, `git remote add origin <url-do-repositorio>` e `git push -u origin main`. A autenticação do GitHub deve estar configurada no seu terminal.

O plano gratuito suspende o serviço após inatividade. Antes da apresentação em aula, abra `/api/health` e aguarde o serviço iniciar. Os limites gratuitos da Gemini API podem variar; confira o painel da sua chave antes da demonstração.

### Incorporação futura no site da disciplina

O administrador do site pode inserir este trecho no HTML/tema MkDocs, substituindo a URL pela URL real do deploy:

```html
<script async src="https://<servico>.onrender.com/widget.js"></script>
```

O script cria um botão de chat que abre a aplicação em um iframe. Até que o responsável pelo site inclua o trecho, a aplicação funciona pela URL própria do Render. Nenhuma alteração no site oficial é necessária para demonstrar o sistema.
