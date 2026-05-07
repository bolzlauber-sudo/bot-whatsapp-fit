import os
import requests
import psycopg2
from flask import Flask, request
from datetime import datetime
import pytz

app = Flask(__name__)

# --- 1. CONFIGURAÇÕES ---
# Mantive a URL base limpa para evitar erros de barras duplicadas
EVO_URL = "https://evolution-api-production-1fac.up.railway.app"
EVO_KEY = "bolzlauber64"
INSTANCIA = "Personal_Bot"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

LINKS_AFILIADO = {
    "CREATINA": "https://meli.la/1QDAB5o",
    "WHEY": "https://meli.la/22YCUoj",
    "GERAL": "https://meli.la/1CPN7GJ"
}

# --- 2. BANCO DE DADOS ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# Inicializa a tabela se não existir
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS historico (
            id SERIAL PRIMARY KEY,
            numero TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Erro no Banco: {e}")

def obter_saudacao_periodo():
    fuso = pytz.timezone('America/Sao_Paulo')
    hora = datetime.now(fuso).hour
    if 5 <= hora < 12: return "Bom dia! Já mandou o café da manhã pra dentro?"
    elif 12 <= hora < 18: return "Boa tarde! Bora que o foco não pode parar!"
    else: return "Boa noite! Disciplina até o fim do dia, hein?"

@app.route("/webhook", methods=["POST"])
def webhook():
    dados = request.get_json()
    
    if dados.get("event") == "messages.upsert":
        try:
            data = dados.get('data', {})
            numero_jid = data.get('key', {}).get('remoteJid')
            nome = data.get('pushName', 'Campeão')
            
            # Pega o texto da mensagem com segurança
            msg_obj = data.get('message', {})
            msg = (msg_obj.get('conversation') or 
                   msg_obj.get('extendedTextMessage', {}).get('text') or "")

            if not msg or not numero_jid:
                return "OK", 200

            # --- A. HISTÓRICO NO BANCO ---
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO historico (numero, role, content) VALUES (%s, %s, %s)", (numero_jid, 'user', msg))
            cur.execute("SELECT role, content FROM historico WHERE numero = %s ORDER BY timestamp DESC LIMIT 8", (numero_jid,))
            rows = cur.fetchall()
            historico = [{"role": r, "content": c} for r, c in reversed(rows)]
            
            # --- B. RESPOSTA DA IA ---
            prompt = (f"Você é o Coach Max. {obter_saudacao_periodo()} Cliente: {nome}. "
                      f"Seja motivador e use estes links se necessário: {LINKS_AFILIADO}")
            
            messages = [{"role": "system", "content": prompt}] + historico

            res_ai = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": messages},
                headers={"Authorization": f"Bearer {OPENAI_KEY}"}
            ).json()
            
            resposta_texto = res_ai['choices'][0]['message']['content']

            # --- C. SALVAR E ENVIAR ---
            cur.execute("INSERT INTO historico (numero, role, content) VALUES (%s, %s, %s)", (numero_jid, 'assistant', resposta_texto))
            conn.commit()
            cur.close()
            conn.close()

            # Ajuste de URL e Número para a Evolution
            numero_puro = numero_jid.split('@')[0]
            url_envio = f"{EVO_URL}/message/sendText/{INSTANCIA}"
            
            payload = {"number": numero_puro, "text": resposta_texto}
            headers = {"Content-Type": "application/json", "apikey": EVO_KEY}

            res_envio = requests.post(url_envio, json=payload, headers=headers)
            print(f"LOG ENVIO: Status {res_envio.status_code} - Resposta: {res_envio.text}")

        except Exception as e:
            print(f"ERRO NO PROCESSO: {e}")

    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))