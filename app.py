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

def log_print(mensagem):
    print(f"===> COACH_MAX_LOG: {mensagem}", file=sys.stderr, flush=True)

# --- FUNÇÃO RESET TOTAL DO BANCO ---
def inicializar_banco():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        log_print("A apagar tabela antiga para reset...")
        cur.execute("DROP TABLE IF EXISTS memoria_usuario CASCADE")
        
        log_print("A criar nova tabela com todas as colunas...")
        cur.execute("""
            CREATE TABLE memoria_usuario (
                jid TEXT PRIMARY KEY,
                contexto TEXT,
                data_vencimento DATE NOT NULL,
                pago BOOLEAN DEFAULT FALSE,
                ja_se_apresentou BOOLEAN DEFAULT FALSE
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        log_print("BANCO DE DADOS RESETADO E PRONTO!")
    except Exception as e:
        log_print(f"ERRO CRÍTICO NO RESET: {e}")

# Executa o reset assim que o app ligar
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
                nova_data = datetime.now().date() + timedelta(days=30)
                conn = psycopg2.connect(DATABASE_URL)
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO memoria_usuario (jid, data_vencimento, pago, ja_se_apresentou) 
                    VALUES (%s, %s, TRUE, TRUE)
                    ON CONFLICT (jid) DO UPDATE SET data_vencimento = %s, pago = TRUE, ja_se_apresentou = TRUE
                """, (numero_jid, nova_data, nova_data))
                conn.commit()
                cur.close()
                conn.close()
                
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                              json={"number": numero_jid, "text": "✅ *ACESSO LIBERADO!*"}, headers={"apikey": EVO_KEY})
                return "OK", 200

            if from_me: return "OK", 200

            # --- VERIFICAÇÃO DE ACESSO ---
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT data_vencimento, pago FROM memoria_usuario WHERE jid = %s", (numero_jid,))
            res = cur.fetchone()
            cur.close()
            conn.close()

            autorizado = False
            if res and res[1]: # Se pago for True
                if res[0] >= datetime.now().date():
                    autorizado = True

            if not autorizado:
                msg_pix = "🚀 *COACH MAX I.A*\n\nPara acesso, faça o PIX: 42988065394 (R$ 15,00)"
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                              json={"number": numero_jid, "text": msg_pix}, headers={"apikey": EVO_KEY})
                return "OK", 200

            # --- RESPOSTA DA IA ---
            res_ai = requests.post("https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-3.5-turbo", 
                    "messages": [{"role": "system", "content": "Você é o Coach Max."}, {"role": "user", "content": texto}]
                },
                headers={"Authorization": f"Bearer {OPENAI_KEY}"}, timeout=25
            )
            resposta_ia = res_ai.json()['choices'][0]['message']['content']
            requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                          json={"number": numero_jid, "text": resposta_ia}, headers={"apikey": EVO_KEY})

        except Exception as e:
            log_print(f"Erro: {e}")
    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))