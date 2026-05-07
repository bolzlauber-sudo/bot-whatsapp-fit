import os
import requests
import sys
from flask import Flask, request

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
EVO_URL = "https://evolution-api-production-1fac.up.railway.app"
EVO_KEY = "A9A38878F984-40BF-88BD-15FA346F642D"
INSTANCIA = "Personal_Bot"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

def log_print(mensagem):
    # O flush=True força o Render a mostrar o log na hora
    print(f"===> COACH_MAX_LOG: {mensagem}", file=sys.stderr, flush=True)

@app.route("/webhook", methods=["POST"])
def webhook():
    dados = request.get_json()
    
    # Filtra apenas mensagens recebidas (ignora atualizações de status)
    if dados.get("event") == "messages.upsert":
        try:
            data = dados.get("data", {})
            numero_jid = data.get("key", {}).get("remoteJid")
            
            # Pega o texto da mensagem
            msg_obj = data.get("message", {})
            texto_usuario = msg_obj.get("conversation") or \
                            msg_obj.get("extendedTextMessage", {}).get("text") or ""

            if not texto_usuario or not numero_jid:
                return "OK", 200

            log_print(f"Mensagem recebida: {texto_usuario}")

            # 1. Chamada para OpenAI
            log_print("Chamando OpenAI...")
            res_ai = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-3.5-turbo", # Trocamos para o 3.5 para teste de estabilidade
                    "messages": [
                        {"role": "system", "content": "Você é o Coach Max, motivador de treinos."}, 
                        {"role": "user", "content": texto_usuario}
                    ]
                },
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                timeout=25
            )
            
            resposta_json = res_ai.json()

            # Verificação de erro da OpenAI
            if 'choices' not in resposta_json:
                log_print(f"ERRO DETALHADO DA OPENAI: {resposta_json}")
                return "OK", 200

            resposta_ia = resposta_json['choices'][0]['message']['content']
            log_print(f"IA respondeu com sucesso.")

            # 2. Envio para Evolution API
            url_envio = f"{EVO_URL}/message/sendText/{INSTANCIA}"
            payload = {
                "number": numero_jid, 
                "text": resposta_ia
            }
            headers = {
                "apikey": EVO_KEY,
                "Content-Type": "application/json"
            }
            
            log_print(f"Devolvendo resposta para o WhatsApp...")
            envio = requests.post(url_envio, json=payload, headers=headers, timeout=25)
            
            log_print(f"STATUS FINAL EVOLUTION: {envio.status_code} - {envio.text}")

        except Exception as e:
            log_print(f"ERRO CRÍTICO NO CÓDIGO: {str(e)}")

    return "OK", 200

if __name__ == "__main__":
    # Porta 10000 é a padrão do Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)