import os
import requests
import psycopg2
from flask import Flask, request
from datetime import datetime
import pytz

app = Flask(__name__)

# --- 1. CONFIGURAÇÕES (Preencha com seus dados) ---
EVO_URL = "https://evolution-api-production-1fac.up.railway.app"
EVO_KEY = "bolzlauber64" # Aquela que você criou na Railway
INSTANCIA = "Personal_Bot"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

# --- 2. SEUS LINKS DE AFILIADO MERCADO LIVRE ---
LINKS_AFILIADO = {
    "CREATINA": "https://meli.la/1QDAB5o",
    "WHEY": "https://meli.la/22YCUoj",
    "GERAL": "https://meli.la/1CPN7GJ"
}

# --- 3. BANCO DE DADOS E MEMÓRIA ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# Cria a tabela de memória se não existir
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
            numero_jid = dados['data']['key']['remoteJid']
            nome = dados['data'].get('pushName', 'Campeão')
            msg = dados['data']['message'].get('conversation') or \
                  dados['data']['message'].get('extendedTextMessage', {}).get('text', '')

            if not msg: return "OK", 200

            # --- A. SALVAR NA MEMÓRIA E BUSCAR HISTÓRICO ---
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO historico (numero, role, content) VALUES (%s, %s, %s)", (numero_jid, 'user', msg))
            cur.execute("SELECT role, content FROM historico WHERE numero = %s ORDER BY timestamp DESC LIMIT 10", (numero_jid,))
            rows = cur.fetchall()
            historico_formatado = [{"role": r, "content": c} for r, c in reversed(rows)]
            
            # --- B. O "CÉREBRO" DO COACH MAX ---
            system_prompt = (
                f"Você é o Coach Max, Personal e Nutricionista. {obter_saudacao_periodo()} "
                f"O cliente se chama {nome}. Sua missão é ser prático, animado e técnico.\n\n"
                "DIRETRIZES:\n"
                "1. Peça peso, altura e objetivo se for o início.\n"
                "2. Se ele citar cansaço ou falta de força, indique CREATINA: " + LINKS_AFILIADO['CREATINA'] + "\n"
                "3. Se ele citar fome ou falta de proteína, indique WHEY: " + LINKS_AFILIADO['WHEY'] + "\n"
                "4. Adapte treinos para dores ou lesões relatadas no histórico.\n"
                "5. Use negrito, emojis e listas. Seja o coach que todos amam!"
            )

            messages = [{"role": "system", "content": system_prompt}] + historico_formatado

            # --- C. CHAMADA OPENAI ---
            res_ai = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": messages, "temperature": 0.7},
                headers={"Authorization": f"Bearer {OPENAI_KEY}"}
            )
            resposta_texto = res_ai.json()['choices'][0]['message']['content']

            # --- D. SALVAR RESPOSTA E ENVIAR WHATSAPP ---
            cur.execute("INSERT INTO historico (numero, role, content) VALUES (%s, %s, %s)", (numero_jid, 'assistant', resposta_texto))
            conn.commit()
            cur.close()
            conn.close()

            requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                          json={"number": numero_jid, "text": resposta_texto}, 
                          headers={"apikey": EVO_KEY})

        except Exception as e:
            print(f"Erro no processamento: {e}")

    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))