import os
import requests
import sys
import psycopg2
from flask import Flask, request

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
EVO_URL = "https://evolution-api-production-1fac.up.railway.app"
EVO_KEY = "A9A38878F984-40BF-88BD-15FA346F642D"
INSTANCIA = "Personal_Bot"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

def log_print(mensagem):
    print(f"===> COACH_MAX_LOG: {mensagem}", file=sys.stderr, flush=True)

# --- FUNÇÕES DE MEMÓRIA (BANCO DE DADOS) ---
def inicializar_banco():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memoria_usuario (
                jid TEXT PRIMARY KEY,
                contexto TEXT
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        log_print("Banco de dados verificado/inicializado.")
    except Exception as e:
        log_print(f"Erro ao iniciar banco: {e}")

def buscar_memoria(jid):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT contexto FROM memoria_usuario WHERE jid = %s", (jid,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        return res[0] if res else ""
    except:
        return ""

def salvar_memoria(jid, novo_contexto):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO memoria_usuario (jid, contexto) VALUES (%s, %s)
            ON CONFLICT (jid) DO UPDATE SET contexto = EXCLUDED.contexto
        """, (jid, novo_contexto))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log_print(f"Erro ao salvar no banco: {e}")

# Inicializa a tabela ao subir o código
inicializar_banco()

@app.route("/webhook", methods=["POST"])
def webhook():
    dados = request.get_json()
    
    if dados.get("event") == "messages.upsert":
        try:
            data = dados.get("data", {})
            numero_jid = data.get("key", {}).get("remoteJid")
            
            msg_obj = data.get("message", {})
            texto_usuario = msg_obj.get("conversation") or \
                            msg_obj.get("extendedTextMessage", {}).get("text") or ""

            if not texto_usuario or not numero_jid:
                return "OK", 200

            log_print(f"Mensagem de {numero_jid}: {texto_usuario}")

            # Recupera o que ele já sabe sobre você
            contexto_antigo = buscar_memoria(numero_jid)

            # 1. Chamada para OpenAI com MEMÓRIA
            log_print("Chamando OpenAI com contexto...")
            res_ai = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-3.5-turbo", 
                    "messages": [
                        {
                            "role": "system", 
                            "content": (
                                "Você é o Coach Max, um assistente fitness motivador e direto. "
                                "Você tem acesso ao histórico do usuário abaixo. Use-o para lembrar nomes, pesos e dores. "
                                "Seja prestativo: dê receitas, sugira exercícios para dores no ombro (com cautela) e envie links. "
                                "Histórico atual: " + contexto_antigo
                            )
                        }, 
                        {"role": "user", "content": texto_usuario}
                    ]
                },
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                timeout=25
            )
            
            resposta_json = res_ai.json()

            if 'choices' not in resposta_json:
                log_print(f"ERRO OPENAI: {resposta_json}")
                return "OK", 200

            resposta_ia = resposta_json['choices'][0]['message']['content']
            
            # Atualiza a memória (guarda o que você disse e o que ele respondeu)
            novo_contexto = (contexto_antigo + f" | Usuário: {texto_usuario} | Coach: {resposta_ia}")[-2000:] # Limite de texto
            salvar_memoria(numero_jid, novo_contexto)

            # 2. Envio para Evolution API
            url_envio = f"{EVO_URL}/message/sendText/{INSTANCIA}"
            payload = {"number": numero_jid, "text": resposta_ia}
            headers = {"apikey": EVO_KEY, "Content-Type": "application/json"}
            
            requests.post(url_envio, json=payload, headers=headers, timeout=25)
            log_print("Resposta enviada com sucesso.")

        except Exception as e:
            log_print(f"ERRO NO PROCESSO: {str(e)}")

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)