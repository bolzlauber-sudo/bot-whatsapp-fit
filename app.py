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
MEU_NUMERO = "554288342887" # Garanta que esse é o número que aparece no log da API

MSG_PAGAMENTO = (
    "🚀 *PRONTO PARA COMEÇAR?*\n\n"
    "Para liberar seu acesso VIP agora, efetue o pagamento da mensalidade:\n\n"
    "💰 *Valor:* R$ 15,00\n"
    "🔑 *PIX (Celular):* 42988065394\n\n"
    "Após pagar, *envie o comprovante aqui no chat* para o Henrique liberar seu acesso! 🔥"
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
                data_vencimento DATE,
                pago BOOLEAN DEFAULT FALSE,
                ja_se_apresentou BOOLEAN DEFAULT FALSE
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log_print(f"Erro ao iniciar banco: {e}")

def verificar_usuario(jid):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT data_vencimento, pago, ja_se_apresentou FROM memoria_usuario WHERE jid = %s", (jid,))
        res = cur.fetchone()
        
        if not res:
            cur.execute("INSERT INTO memoria_usuario (jid, pago, ja_se_apresentou) VALUES (%s, FALSE, FALSE)", (jid,))
            conn.commit()
            cur.close()
            conn.close()
            return False, "novo", False
        
        cur.close()
        conn.close()
        vencimento, pago, apresentado = res
        
        hoje = datetime.now().date()
        if not pago: return False, "nao_pago", apresentado
        if vencimento < hoje: return False, "vencido", apresentado
        
        return True, "liberado", apresentado
    except Exception as e:
        log_print(f"Erro verificar user: {e}")
        return False, "erro", True

def liberar_aluno(jid):
    try:
        nova_data = datetime.now().date() + timedelta(days=30)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Aqui o comando força o PAGO como TRUE e atualiza a data
        cur.execute("""
            INSERT INTO memoria_usuario (jid, data_vencimento, pago, ja_se_apresentou) 
            VALUES (%s, %s, TRUE, TRUE)
            ON CONFLICT (jid) DO UPDATE SET data_vencimento = %s, pago = TRUE, ja_se_apresentou = TRUE
        """, (jid, nova_data, nova_data))
        conn.commit()
        cur.close()
        conn.close()
        log_print(f"Usuário {jid} LIBERADO até {nova_data}")
        return True
    except Exception as e:
        log_print(f"Erro ao liberar no banco: {e}")
        return False

inicializar_banco()

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
            # Melhoria: Aceita com ou sem maiúsculas
            if from_me and texto.lower() == "#liberar":
                if liberar_aluno(numero_jid):
                    resp = "✅ *ACESSO VIP LIBERADO POR 30 DIAS!*\n\nCoach Max está pronto. Como posso te ajudar hoje?"
                else:
                    resp = "❌ Erro técnico ao liberar no banco de dados."
                
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                              json={"number": numero_jid, "text": resp}, headers={"apikey": EVO_KEY})
                return "OK", 200

            # --- SE FOR VOCÊ MANDANDO MENSAGEM (Ignore travas) ---
            if from_me: return "OK", 200

            # --- VERIFICAÇÃO DE ACESSO ---
            autorizado, status, ja_apresentou = verificar_usuario(numero_jid)

            if not autorizado:
                msg_bloqueio = "⏳ *SUA ASSINATURA VENCEU!*\n\n" + MSG_PAGAMENTO if status == "vencido" else MSG_PAGAMENTO
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                              json={"number": numero_jid, "text": msg_bloqueio}, headers={"apikey": EVO_KEY})
                return "OK", 200

            # --- RESPOSTA DA IA ---
            if texto:
                res_ai = requests.post("https://api.openai.com/v1/chat/completions",
                    json={
                        "model": "gpt-3.5-turbo", 
                        "messages": [
                            {"role": "system", "content": "Você é o Coach Max, assistente fitness VIP."},
                            {"role": "user", "content": texto}
                        ]
                    },
                    headers={"Authorization": f"Bearer {OPENAI_KEY}"}, timeout=25
                )
                resposta_ia = res_ai.json()['choices'][0]['message']['content']
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", 
                              json={"number": numero_jid, "text": resposta_ia}, headers={"apikey": EVO_KEY})

        except Exception as e:
            log_print(f"Erro geral: {e}")
    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))