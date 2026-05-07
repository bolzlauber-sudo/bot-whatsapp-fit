import os
import requests
import psycopg2
from flask import Flask, request
from datetime import datetime
import pytz

app = Flask(__name__)

# --- 1. CONFIGURAÇÕES (Limpas e Organizadas) ---
EVO_URL = "https://evolution-api-production-1fac.up.railway.app"
EVO_KEY = "bolzlauber64"
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

# Inicializa o banco de dados
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
    print("Banco de dados verificado com sucesso!")
except Exception as e:
    print(f"Erro ao conectar no banco: {e}")

def obter_saudacao_periodo():
    fuso = pytz.timezone('America/Sao_Paulo')
    hora = datetime.now(fuso).hour
    if 5 <= hora < 12: return "Bom dia! Já mandou o café da manhã pra dentro?"
    elif 12 <= hora < 18: return "Boa tarde! Bora que o foco não pode parar!"
    else: return "Boa noite! Disciplina até o fim do dia, hein?"

@app.route("/webhook", methods=["POST"])
def webhook():
    dados = request.get_json()
    
    # Verifica se o evento é de mensagem
    if dados.get("event") == "messages.upsert":
        try:
            # Extração de dados da Evolution API v1.x/v2.x
            data = dados['data']
            # Se for v2, a estrutura pode mudar levemente, mas esse padrão é o mais comum:
            numero_jid = data['key']['remoteJid']
            nome = data.get('pushName', 'Campeão')
            
            # Pega o texto da mensagem
            msg = ""
            message_obj = data.get('message', {})
            if 'conversation' in message_obj:
                msg = message_obj['conversation']
            elif 'extendedTextMessage' in message_obj:
                msg = message_obj['extendedTextMessage'].get('text', '')

            if not msg: 
                return "OK", 200

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
            
            resposta_json = res_ai.json()
            if 'choices' in resposta_json:
                resposta_texto = resposta_json['choices'][0]['message']['content']
            else:
                print(f"Erro OpenAI: {resposta_json}")
                return "Erro OpenAI", 500

            # --- D. SALVAR RESPOSTA E ENVIAR WHATSAPP ---
            cur.execute("INSERT INTO historico (numero, role, content) VALUES (%s, %s, %s)", (numero_jid, 'assistant', resposta_texto))
            conn.commit()
            cur.close()
            conn.close()

            # Limpa o JID para enviar apenas o número (ex: 551199999999)
            numero_puro = numero_jid.split('@')[0]

            # Envia para a Evolution
            url_final = f"{EVO_URL}/message/sendText/{INSTANCIA}"
            payload = {
                "number": numero_puro,
                "text": resposta_texto
            }
            
            envio = requests.post(url_final, json=payload, headers={"apikey": EVO_KEY})
            print(f"Status Envio: {envio.status_code} - Resposta: {envio.text}")

        except Exception as e:
            print(f"Erro no processamento: {e}")

    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))