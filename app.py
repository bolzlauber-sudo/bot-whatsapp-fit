from flask import Flask, request
import requests

app = Flask(__name__)

API_KEY = "SUA_API_KEY_AQUI"

# memória simples dos usuários
usuarios = {}

@app.route("/webhook", methods=["POST"])
def webhook():
    mensagem = request.form.get("Body")
    numero = request.form.get("From")

    if not mensagem:
        return "Manda um objetivo aí 💪"

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

Histórico recente:
{historico}

Crie uma resposta com:

1. Treino semanal (simples e eficiente)
2. Dieta básica (barata e prática)
3. Dicas diretas
4. Motivação forte (estilo coach raiz)

Seja curto, direto e impactante.
"""

    try:
        resposta = requests.post(
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

        texto = resposta.json()["choices"][0]["message"]["content"]

    except:
        texto = "Erro na IA, tenta de novo 💪"

    return texto

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)