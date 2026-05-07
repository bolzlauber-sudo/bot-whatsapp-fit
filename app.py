import os
import requests
import sys
from flask import Flask, request

app = Flask(__name__)

# --- CONFIGURAÇÕES DIRETAS (Ajustadas conforme seus logs) ---
EVO_URL = "https://evolution-api-production-1fac.up.railway.app"
EVO_KEY = "A9A38878F984-40BF-88BD-15FA346F642D"
INSTANCIA = "Personal_Bot"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

def log_print(mensagem):
    print(f"===> COACH_MAX_LOG: {mensagem}", file=sys.stderr, flush=True)

@app.route("/webhook", methods=["POST"])
def webhook():
    dados = request.get_json()
    
    # Log para sabermos que a mensagem chegou no Render
    log_print(f"Webhook recebido! Evento: {dados.get('event')}")

    if dados.get("event") == "messages.upsert":
        try:
            data = dados.get("data", {})
            numero_jid = data.get("key", {}).get("remoteJid")
            
            # Captura o texto da mensagem
            msg_obj = data.get("message", {})
            texto_usuario = msg_obj.get("conversation") or \
                            msg_obj.get("extendedTextMessage", {}).get("text") or ""

            if not texto_usuario or not numero_jid:
                return "OK", 200

            log_print(f"Mensagem do usuário: {texto_usuario}")

            # 1. Chamada para OpenAI
            log_print("Chamando OpenAI...")
            res_ai = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4o-mini", 
                    "messages": [
                        {"role": "system", "content": "Você é o Coach Max, um assistente de treinos motivador e direto."}, 
                        {"role": "user", "content": texto_usuario}
                    ]
                },
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                timeout=20
            )
            
            resposta_ia = res_ai.json()['choices'][0]['message']['content']
            log_print(f"IA respondeu: {resposta_ia[:30]}...")

            # 2. Envio de volta para o WhatsApp via Evolution
            url_envio = f"{EVO_URL}/message/sendText/{INSTANCIA}"
            payload = {
                "number": numero_jid, 
                "text": resposta_ia,
                "delay": 1000
            }
            headers = {
                "apikey": EVO_KEY,
                "Content-Type": "application/json"
            }
            
            log_print(f"Enviando resposta para {numero_jid}...")
            envio = requests.post(url_envio, json=payload, headers=headers, timeout=20)
            
            log_print(f"STATUS FINAL EVOLUTION: {envio.status_code} - {envio.text}")

        except Exception as e:
            log_print(f"ERRO NO PROCESSO: {str(e)}")

    return "OK", 200

if __name__ == "__main__":
    # Porta padrão do Render é 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)