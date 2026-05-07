import os
import requests
import psycopg2
from flask import Flask, request
from datetime import datetime
import pytz

app = Flask(__name__)

# --- 1. CONFIGURAÇÕES CORRIGIDAS ---
EVO_URL = "https://evolution-api-production-1fac.up.railway.app"
# CHAVE RETIRADA DO SEU LOG DA RAILWAY:
EVO_KEY = "A9A38878F984-40BF-88BD-15FA346F642D"
INSTANCIA = "Personal_Bot"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

LINKS_AFILIADO = {
    "CREATINA": "https://meli.la/1QDAB5o",
    "WHEY": "https://meli.la/22YCUoj",
    "GERAL": "https://meli.la/1CPN7GJ"
}

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# Inicializa tabela
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS historico (id SERIAL PRIMARY KEY, numero TEXT, role TEXT, content TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.commit()
    cur.close()
    conn.close()
except:
    pass

@app.route("/webhook", methods=["POST"])
def webhook():
    dados = request.get_json()
    if not dados or "data" not in dados:
        return "OK", 200

    try:
        data_body = dados.get("data", {})
        numero_jid = data_body.get("key", {}).get("remoteJid")
        nome = data_body.get("pushName", "Campeão")
        
        message = data_body.get("message", {})
        msg = (message.get("conversation") or 
               message.get("extendedTextMessage", {}).get("text") or "")

        if not msg or not numero_jid:
            return "OK", 200

        # 1. Banco
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO historico (numero, role, content) VALUES (%s, %s, %s)", (numero_jid, 'user', msg))
        cur.execute("SELECT role, content FROM historico WHERE numero = %s ORDER BY timestamp DESC LIMIT 6", (numero_jid,))
        rows = cur.fetchall()
        historico = [{"role": r, "content": c} for r, c in reversed(rows)]

        # 2. OpenAI
        prompt = f"Você é o Coach Max. Cliente: {nome}. Use os links: {LINKS_AFILIADO}"
        messages = [{"role": "system", "content": prompt}] + historico
        
        res_ai = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": messages},
            headers={"Authorization": f"Bearer {OPENAI_KEY}"}
        ).json()
        
        resposta_texto = res_ai['choices'][0]['message']['content']

        # 3. Enviar para WhatsApp (Evolution)
        numero_puro = numero_jid.split('@')[0]
        url_final = f"{EVO_URL}/message/sendText/{INSTANCIA}"
        
        payload = {"number": numero_puro, "text": resposta_texto}
        headers = {"apikey": EVO_KEY, "Content-Type": "application/json"}
        
        envio = requests.post(url_final, json=payload, headers=headers)
        print(f"RESPOSTA EVOLUTION: {envio.status_code} - {envio.text}")

        cur.execute("INSERT INTO historico (numero, role, content) VALUES (%s, %s, %s)", (numero_jid, 'assistant', resposta_texto))
        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"ERRO: {e}")

    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))