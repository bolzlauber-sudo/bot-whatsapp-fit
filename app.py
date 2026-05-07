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

# --- MENSAGENS PADRONIZADAS ---
MSG_BOAS_VINDAS = (
    "👋 *Olá! Sou o Coach Max I.A.*\n\n"
    "Vou te ajudar com:\n"
    "✅ Treinos Personalizados\n"
    "✅ Sugestões de Dietas\n"
    "✅ Dicas de Suplementação\n"
    "✅ Sua Agenda de Evolução\n\n"
    "------------------------------------------\n"
    "🚀 *LIBERE SEU ACESSO VIP:*\n\n"
    "💰 *Valor:* R$ 15,00 (Mensal)\n"
    "🔑 *PIX (Celular):* 42988065394\n\n"
    "Após pagar, *envie o comprovante aqui no chat* para liberar seu acesso agora! 🔥"
)

def log_print(mensagem):
    print(f"===> COACH_MAX_LOG: {mensagem}", file=sys.stderr, flush=True)

def inicializar_banco():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memoria_usuario (
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
        log_print("Banco de dados pronto!")
    except Exception as e:
        log_print(f"Erro banco: {e}")

def obter_info_aluno(jid):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT data_vencimento, pago FROM memoria_usuario WHERE jid = %s", (jid,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        if res:
            vencimento, pago = res
            dias_restantes = (vencimento - datetime.now().date()).days
            return pago, dias_restantes
        return False, 0
    except:
        return False, 0

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
                
                msg_sucesso = "✅ *ACESSO VIP LIBERADO!*\n\nSua assinatura vale por 30 dias. Aproveite o Coach Max! 🔥"
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                              json={"number": numero_jid, "text": msg_sucesso}, headers={"apikey": EVO_KEY})
                return "OK", 200

            if from_me: return "OK", 200

            # --- VERIFICAÇÃO DE STATUS ---
            pago, dias = obter_info_aluno(numero_jid)
            
            # Se não está pago ou venceu
            if not pago or dias < 0:
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                              json={"number": numero_jid, "text": MSG_BOAS_VINDAS}, headers={"apikey": EVO_KEY})
                return "OK", 200

            # --- RESPOSTA DA IA ---
            # Aqui damos o contexto dos dias restantes para a IA saber responder
            prompt_sistema = f"Você é o Coach Max, assistente fitness. O aluno tem {dias} dias de assinatura restante. Se ele perguntar sobre o tempo, diga: 'Você tem {dias} dias de assinatura, aproveite!'. Seja motivador."

            res_ai = requests.post("https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-3.5-turbo", 
                    "messages": [
                        {"role": "system", "content": prompt_sistema},
                        {"role": "user", "content": texto}
                    ]
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