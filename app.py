import os
from flask import Flask, request
import requests
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# Puxa a chave que você configurou no painel do Render
API_KEY = os.environ.get("API_KEY")

# memória simples dos usuários
usuarios = {}

@app.route("/webhook", methods=["POST"])
def webhook():
    mensagem = request.form.get("Body")
    numero = request.form.get("From")

    # Prepara a resposta da Twilio
    resp = MessagingResponse()

    if not mensagem:
        resp.message("Manda um objetivo aí 💪")
        return str(resp)

    # cria perfil do usuário
    if numero not in usuarios:
        usuarios[numero] = {
            "historico": [],
            "nivel": "iniciante"
        }

    usuarios[numero]["historico"].append(mensagem)
    historico = "\n".join(usuarios[numero]["historico"][-3:])

    prompt = f"""
Você é um PERSONAL TRAINER RAIZ, estilo motivador, direto e sem enrolação.
Fale como um coach de academia que quer resultado REAL.
Cliente disse agora: {mensagem}
Histórico recente: {historico}

Crie uma resposta com:
1. Treino semanal (simples e eficiente)
2. Dieta básica (barata e prática)
3. Dicas diretas
4. Motivação forte (estilo coach raiz)

Seja curto, direto e impactante.
"""

    try:
        requisicao = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
        )

        dados = requisicao.json()
        texto = dados["choices"][0]["message"]["content"]

    except Exception as e:
        print(f"Erro detalhado: {e}")
        texto = "Erro na IA, tenta de novo 💪"

    # O SEGREDO ESTÁ AQUI: Devolve no formato que o WhatsApp entende
    resp.message(texto)
    return str(resp)

if __name__ == "__main__":
    # Configuração correta para o Render rodar
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)