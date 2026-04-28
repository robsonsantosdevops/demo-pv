-- Migration: esquema unificado (baseado em init.sql + init1.sql)
-- Aplicar na base: poliedro_db
--
-- Exemplo:
--   psql -U postgres -d poliedro_db -f init.sql
--   kubectl exec -i deploy/postgres -n demo -- psql -U postgres -d poliedro_db < init.sql
--
-- Diferenças face ao init.sql antigo:
-- - pagamentos.status DEFAULT alinhado ao modelo (Pagamento.js usa 'aprovado').
-- - pedidos.correlation_id + índice (Pedido.js INSERT exige esta coluna).
-- - pedido_itens.curso_id como VARCHAR (itens do front podem ser IDs não numéricos).

-- ============================================================
-- 1. ALUNOS
-- ============================================================
CREATE TABLE IF NOT EXISTS alunos (
    id SERIAL PRIMARY KEY,
    nome_completo VARCHAR(255) NOT NULL,
    cpf VARCHAR(11) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    telefone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alunos_cpf ON alunos(cpf);
CREATE INDEX IF NOT EXISTS idx_alunos_email ON alunos(email);
CREATE INDEX IF NOT EXISTS idx_alunos_created_at ON alunos(created_at);

-- ============================================================
-- 2. PAGAMENTOS
-- ============================================================
CREATE TABLE IF NOT EXISTS pagamentos (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    forma_pagamento VARCHAR(50) NOT NULL,
    responsavel_financeiro BOOLEAN DEFAULT FALSE,
    valor DECIMAL(10, 2) NOT NULL,
    parcelas INTEGER,
    cartao_numero VARCHAR(16),
    cartao_validade VARCHAR(5),
    cartao_nome VARCHAR(255),
    cartao_recorrente BOOLEAN DEFAULT FALSE,
    protocolo VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(50) DEFAULT 'aprovado',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pagamentos_aluno_id ON pagamentos(aluno_id);
CREATE INDEX IF NOT EXISTS idx_pagamentos_protocolo ON pagamentos(protocolo);
CREATE INDEX IF NOT EXISTS idx_pagamentos_status ON pagamentos(status);
CREATE INDEX IF NOT EXISTS idx_pagamentos_created_at ON pagamentos(created_at);

-- ============================================================
-- 3. PEDIDOS (correlation_id obrigatório para o fluxo atual da API)
-- ============================================================
CREATE TABLE IF NOT EXISTS pedidos (
    id SERIAL PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    numero_pedido VARCHAR(100) NOT NULL UNIQUE,
    correlation_id VARCHAR(100),
    status VARCHAR(50) DEFAULT 'aguardando_pagamento',
    total DECIMAL(10, 2) NOT NULL,
    parcelas INTEGER,
    forma_pagamento VARCHAR(50),
    pagamento_id INTEGER REFERENCES pagamentos(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pedidos_aluno_id ON pedidos(aluno_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_numero_pedido ON pedidos(numero_pedido);
CREATE INDEX IF NOT EXISTS idx_pedidos_status ON pedidos(status);
CREATE INDEX IF NOT EXISTS idx_pedidos_pagamento_id ON pedidos(pagamento_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_created_at ON pedidos(created_at);
CREATE INDEX IF NOT EXISTS idx_pedidos_correlation_id ON pedidos(correlation_id);

-- ============================================================
-- 4. ITENS DO PEDIDO
-- ============================================================
CREATE TABLE IF NOT EXISTS pedido_itens (
    id SERIAL PRIMARY KEY,
    pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    curso_id VARCHAR(100),
    curso_titulo VARCHAR(255) NOT NULL,
    quantidade INTEGER NOT NULL DEFAULT 1,
    preco_unitario DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pedido_itens_pedido_id ON pedido_itens(pedido_id);
CREATE INDEX IF NOT EXISTS idx_pedido_itens_curso_id ON pedido_itens(curso_id);
CREATE INDEX IF NOT EXISTS idx_pedido_itens_created_at ON pedido_itens(created_at);

-- ============================================================
-- 5. Atualização incremental (BD já criada com init.sql antigo)
-- ============================================================
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(100);
CREATE INDEX IF NOT EXISTS idx_pedidos_correlation_id ON pedidos(correlation_id);

-- Se pedido_itens.curso_id ainda for INTEGER de uma versão antiga, promove para texto.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pedido_itens'
          AND column_name = 'curso_id'
          AND data_type = 'integer'
    ) THEN
        ALTER TABLE pedido_itens
            ALTER COLUMN curso_id TYPE VARCHAR(100)
            USING curso_id::text;
    END IF;
END $$;

-- ============================================================
-- 6. Permissões (evita 42501 "permission denied for table ...")
-- O utilizador em DB_USER (Secret) tem de poder ler/escrever nas tabelas.
-- Se as tabelas foram criadas como postgres e a API liga como "app", concede-se a esse role.
-- ============================================================
DO $$
DECLARE
    r TEXT;
BEGIN
    -- Lista de roles típicos da API; acrescenta o mesmo nome que DB_USER no Secret.
    FOREACH r IN ARRAY ARRAY['app', 'poliedro']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', r);
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', r);
            EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I', r);
        END IF;
    END LOOP;
END $$;

DO $$
BEGIN
    RAISE NOTICE 'Schema poliedro_db: tabelas alunos, pagamentos, pedidos, pedido_itens verificadas.';
END $$;
