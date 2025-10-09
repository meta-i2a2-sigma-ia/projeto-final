# Guia de Instalação e Subida de Ambiente

Este documento descreve como preparar todos os componentes do projeto **sigma-ia2a**: aplicação Streamlit (EDA/autogen), pipeline de ingestão S3 ➝ Supabase (AWS Lambda) e dependências de infraestrutura. Os passos são apresentados em ordem sugerida, mas você pode executar apenas as seções relevantes ao seu cenário (ex.: apenas desenvolvimento local).

## 1. Pré-requisitos
- Git e um terminal com `bash`/`zsh`.
- **Python 3.11** e `pip` atualizados (`python3 --version`).
- **Docker** + **Docker Compose** (plugin integrado funciona).
- **Terraform ≥ 1.5.7** (`terraform -version`).
- **AWS CLI v2** configurado com credenciais que tenham permissões para S3, Lambda, IAM e CloudWatch (`aws configure`).
- Conta Supabase com acesso ao **Project Settings → API** (para coletar URL e Service Role Key) e ao **SQL Editor**.
- Conta OpenAI com uma **API key** habilitada para o modelo em uso (default `gpt-4o-mini`).

> Dica: após instalar, valide cada ferramenta rodando o comando `--version` correspondente.

## 2. Clonar o repositório
```bash
git clone <url-do-repo>
cd sigma-ia2a
```
Se você já possui o diretório clonado, apenas entre na pasta de trabalho.

## 3. Configurar variáveis sensíveis (`.env`)
A aplicação lê variáveis pela shell ou via `eda/.env` (respeitando a convenção do Docker Compose). Crie `eda/.env` com o seguinte conteúdo (substitua pelos seus valores reais):
```env
OPENAI_API_KEY="sk-..."
OPENAI_MODEL="gpt-4o-mini"
SUPABASE_URL="https://<seu-projeto>.supabase.co"
SUPABASE_SERVICE_ROLE_KEY="<service-role-key>"
PG_SCHEMA="public"
DEFAULT_TABLE="s3_creditcard"
ALLOW_DANGEROUS_CODE="0"
```
- `ALLOW_DANGEROUS_CODE=1` habilita o REPL Python do agente – mantenha desligado fora de ambientes controlados.
- Você pode manter esse arquivo fora do versionamento (`git update-index --skip-worktree eda/.env` ou via `.gitignore`).

## 4. Preparar o Supabase
1. Acesse o **SQL Editor** do seu projeto Supabase.
2. Execute o script `database/supabasev4.sql` (versão mais recente) para criar a função `ensure_table`, utilizada pela Lambda para criar/ajustar tabelas automaticamente.
3. Confirme que a função aparece em **Database → Functions** e possui permissões apenas para o `service_role`.
4. Opcional: execute scripts anteriores (`supabase.sql`, `supabasev2.sql`, etc.) apenas se precisar comparar evoluções; a versão `v4` já consolida o comportamento atual.

## 5. Rodar a aplicação EDA localmente (Docker)
Esta é a forma mais rápida de subir a UI.
```bash
cd eda
docker compose build
docker compose up
```
- O Streamlit ficará disponível em `http://localhost:8501`.
- O container lê as variáveis do arquivo `eda/.env` criado na etapa 3.
- Para derrubar, use `Ctrl+C` e depois `docker compose down`.

## 6. Rodar a aplicação EDA localmente (virtualenv)
Caso prefira executar sem Docker:
```bash
cd eda
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```
- O Streamlit abre em `http://localhost:8501`.
- Para encerrar, pressione `Ctrl+C`; desative o ambiente com `deactivate`.

## 7. Pipeline de ingestão S3 ➝ Supabase (AWS Lambda)
A infraestrutura está descrita em Terraform nos arquivos da raiz do projeto.

1. **Configurar `terraform.tfvars`:**
   - Copie `terraform.tfvars` para algo como `terraform.auto.tfvars` e substitua **todos** os valores sensíveis (`supabase_service_role_key`, `supabase_access_token`, etc.) pelos seus próprios segredos. Nunca reutilize credenciais de exemplo em produção.
   - Garanta que `s3_bucket_name` é único globalmente.
2. **Inicializar Terraform:**
   ```bash
   terraform init
   ```
3. **Planejar e aplicar:**
   ```bash
   terraform plan
   terraform apply
   ```
   - Confirme os recursos que serão criados: bucket S3, função Lambda, permissões IAM e notificações.
   - O pacote da Lambda é gerado automaticamente a partir do diretório `lambda/` usando o recurso `archive_file`.
4. **Variáveis de ambiente da Lambda:**
   - Durante `terraform apply`, o módulo injeta as variáveis (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `TABLE_STRATEGY`, etc.) com base no seu `*.tfvars`.
   - Ajuste `TABLE_STRATEGY`, `TABLE_PREFIX`, `SAMPLE_LINES_FOR_INFERENCE` e `BATCH_SIZE` conforme o perfil dos arquivos.
5. **Integração:**
   - Faça upload de arquivos `.csv` (ou com sufixo definido) no bucket S3 configurado. A Lambda sanitiza cabeçalhos, garante colunas TEXT e grava linhas via REST API no Supabase.
   - Monitore logs em `CloudWatch Logs` (grupo `/aws/lambda/<lambda_name>`).

> Para destruir os recursos: `terraform destroy` (cuidado com dados no S3).

## 8. Teste rápido do fluxo end-to-end
1. Faça upload de um CSV pequeno no bucket S3 configurado. Verifique, via Supabase Studio, se a tabela correspondente foi criada/preenchida.
2. Abra `http://localhost:8501`, escolha **Supabase** como fonte e informe schema/tabela para carregar os dados ingeridos.
3. Realize perguntas ao agente; gere um relatório PDF para validar a dependência `kaleido`.

## 9. Troubleshooting básico
- **Docker não sobe / porta ocupada:** verifique se não há outra instância do Streamlit usando `lsof -i :8501`.
- **API da OpenAI retorna erro 401:** confirme `OPENAI_API_KEY` e permissões do modelo (alguns planos exigem habilitação manual).
- **Falha na Lambda (AccessDenied):** revise a role criada (arquivo `main.tf` garante logs + leitura S3, ajuste se precisar de writes adicionais).
- **`ensure_table` não encontrada:** reexecute o script `database/supabasev4.sql` com o usuário `service_role`.

## 10. Próximos passos sugeridos
- Configure pipelines CI/CD para validar o diretório `lambda/` (tests/linters) antes do `terraform apply`.
- Automatize a atualização do container Streamlit com `docker compose build --no-cache app` sempre que alterar código em `eda/`.

Com isso o ambiente completo (local + ingestão na nuvem) estará pronto para uso.
