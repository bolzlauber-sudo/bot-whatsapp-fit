import os
import requests
import sys
import psycopg2
from flask import Flask, request
from datetime import datetime, timedelta

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
EVO_URL = "https://evolution-api-production-1fac.up.railway.app"
EVO_KEY = "A9A38878F984-40BF-88BD-15FA346F642D"
INSTANCIA = "Personal_Bot"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

MSG_PAGAMENTO = (
    "🚀 *PRONTO PARA COMEÇAR?*\n\n"
    "Para liberar seu acesso VIP agora, efetue o pagamento da mensalidade:\n\n"
    "💰 *Valor:* R$ 15,00\n"
    "🔑 *PIX (Celular):* 42988065394\n\n"
    "Após pagar, *envie o comprovante aqui no chat* para que seja liberado seu acesso! 🔥"
)

def log_print(mensagem):
    print(f"===> COACH_MAX_LOG: {mensagem}", file=sys.stderr, flush=True)

# --- INICIALIZAÇÃO COM CORREÇÃO DE TABELA ---
def inicializar_banco():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # 1. Cria a tabela base se não existir
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memoria_usuario (
                jid TEXT PRIMARY KEY,
                contexto TEXT,
                data_vencimento DATE,
                pago BOOLEAN DEFAULT FALSE
            )
        """)
        # 2. Tenta adicionar as colunas novas uma por uma (caso não existam)
        colunas_novas = ["ja_se_apresentou"]
        for col in colunas_novas:
            try:
                cur.execute(f"ALTER TABLE memoria_usuario ADD COLUMN {col} BOOLEAN DEFAULT FALSE")
                log_print(f"Coluna {col} adicionada.")
            except:
                conn.rollback() # Coluna já existe
        
        conn.commit()
        cur.close()
        conn.close()
        log_print("Banco de dados verificado e pronto!")
    except Exception as e:
        log_print(f"ERRO AO INICIAR BANCO: {e}")

def liberar_aluno(jid):
    try:
        nova_data = datetime.now().date() + timedelta(days=30)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Usamos uma query que funciona mesmo se as colunas novas derem erro
        cur.execute("""
            INSERT INTO memoria_usuario (jid, data_vencimento, pago, ja_se_apresentou) 
            VALUES (%s, %s, TRUE, TRUE)
            ON CONFLICT (jid) DO UPDATE SET data_vencimento = %s, pago = TRUE, ja_se_apresentou = TRUE
        """, (jid, nova_data, nova_data))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        log_print(f"ERRO AO SALVAR NO BANCO: {e}")
        return False

# Inicializa o banco ao rodar o app
inicializar_banco()

@app.route("/webhook", methods=["POST"])
def webhook():
    dados = request.get_json()
    if dados.get("event") == "messages.upsert":
        try:
            data = dados.get("data", {})
            numero_jid = data.get("key", {}).get("remoteJid")
            from_me = data.get("key", {}).get("fromMe", False)
            msg_obj = data.get("message", {})
            texto = (msg_obj.get("conversation") or 
                     msg_obj.get("extendedTextMessage", {}).get("text") or "").strip()

            if not numero_jid: return "OK", 200

            # --- COMANDO DE ADMIN (#liberar) ---
            if from_me and texto.lower() == "#liberar":
                if liberar_aluno(numero_jid):
                    resp = "✅ *ACESSO VIP LIBERADO POR 30 DIAS!*\n\nO Coach Max já pode responder você. Tente mandar um 'Oi' agora!"
                else:
                    resp = "❌ Erro ao salvar no banco. Verifique os logs no Render."
                
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                              json={"number": numero_jid, "text": resp}, headers={"apikey": EVO_KEY})
                return "OK", 200

            # --- LÓGICA DE BLOQUEIO ---
            if from_me: return "OK", 200

            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT data_vencimento, pago FROM memoria_usuario WHERE jid = %s", (numero_jid,))
            res = cur.fetchone()
            cur.close()
            conn.close()

            autorizado = False
            if res and res[1]: # Se pago for True
                if res[0] >= datetime.now().date(): # Se não venceu
                    autorizado = True

            if not autorizado:
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                              json={"number": numero_jid, "text": MSG_PAGAMENTO}, headers={"apikey": EVO_KEY})
                return "OK", 200

            # --- RESPOSTA IA (SÓ VIPS) ---
            res_ai = requests.post("https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-3.5-turbo", 
                    "messages": [{"role": "system", "content": "Você é o Coach Max, assistente fitness VIP."}, {"role": "user", "content": texto}]
                },
                headers={"Authorization": f"Bearer {OPENAI_KEY}"}, timeout=25
            )
            resposta_ia = res_ai.json()['choices'][0]['message']['content']
            requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                          json={"number": numero_jid, "text": resposta_ia}, headers={"apikey": EVO_KEY})

        except Exception as e:
            log_print(f"Erro Webhook: {e}")
    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))