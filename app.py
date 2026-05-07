import os
import requests
import sys
import psycopg2
import json
from flask import Flask, request
from datetime import datetime, timedelta

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
EVO_URL = "https://evolution-api-production-1fac.up.railway.app"
EVO_KEY = "A9A38878F984-40BF-88BD-15FA346F642D"
INSTANCIA = "Personal_Bot"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

MSG_BOAS_VINDAS = (
    "👋 *Olá! Sou o Coach Max I.A.*\n\n"
    "Vou te ajudar com treinos e dietas personalizados!\n"
    "------------------------------------------\n"
    "🚀 *LIBERE SEU ACESSO VIP:*\n"
    "💰 *Valor:* R$ 15,00 (Mensal)\n"
    "🔑 *PIX (Celular):* 42988065394\n\n"
    "Após pagar, envie o comprovante para o Henrique liberar você! 🔥"
)

def log_print(mensagem):
    print(f"===> COACH_MAX_LOG: {mensagem}", file=sys.stderr, flush=True)

def gerenciar_memoria(jid, nova_mensagem=None, resposta_ia=None):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT contexto, data_vencimento, pago FROM memoria_usuario WHERE jid = %s", (jid,))
        res = cur.fetchone()
        
        if not res:
            cur.close()
            conn.close()
            return [], False, -1

        historico_json, vencimento, pago = res
        historico = json.loads(historico_json) if historico_json else []
        
        if nova_mensagem and resposta_ia:
            historico.append({"role": "user", "content": nova_mensagem})
            historico.append({"role": "assistant", "content": resposta_ia})
            # Mantemos um histórico maior (15 interações) para preservar dados de peso/altura
            historico = historico[-30:] 
            cur.execute("UPDATE memoria_usuario SET contexto = %s WHERE jid = %s", (json.dumps(historico), jid))
            conn.commit()

        cur.close()
        conn.close()
        dias = (vencimento - datetime.now().date()).days
        return historico, pago, dias
    except Exception as e:
        log_print(f"Erro na memoria: {e}")
        return [], False, -1

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

            # --- COMANDOS ADMIN ---
            if from_me:
                if texto.lower() == "#liberar":
                    nova_data = datetime.now().date() + timedelta(days=30)
                    conn = psycopg2.connect(DATABASE_URL)
                    cur = conn.cursor()
                    cur.execute("UPDATE memoria_usuario SET data_vencimento = %s, pago = TRUE WHERE jid = %s", (nova_data, numero_jid))
                    if cur.rowcount == 0:
                        cur.execute("INSERT INTO memoria_usuario (jid, data_vencimento, pago) VALUES (%s, %s, TRUE)", (numero_jid, nova_data))
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    # Mensagem de Boas-vindas VIP com Pergunta de Perfil
                    msg_vip = (
                        "✅ *ACESSO VIP LIBERADO!*\n\n"
                        "Para começarmos seu plano, por favor me diga:\n"
                        "1️⃣ Qual seu *Nome*?\n"
                        "2️⃣ Qual seu *Peso* atual?\n"
                        "3️⃣ Qual sua *Altura* e idade?\n\n"
                        "Vou guardar esses dados para acompanhar sua evolução! 💪"
                    )
                    requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", json={"number": numero_jid, "text": msg_vip}, headers={"apikey": EVO_KEY})
                    return "OK", 200

                if texto.lower() == "#remover":
                    conn = psycopg2.connect(DATABASE_URL)
                    cur = conn.cursor()
                    cur.execute("DELETE FROM memoria_usuario WHERE jid = %s", (numero_jid,))
                    conn.commit()
                    cur.close()
                    conn.close()
                    requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", json={"number": numero_jid, "text": "🗑️ *RESETADO!*"}, headers={"apikey": EVO_KEY})
                    return "OK", 200
                return "OK", 200

            # --- FLUXO DO ALUNO ---
            historico, pago, dias = gerenciar_memoria(numero_jid)
            
            if not pago or dias < 0:
                requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", json={"number": numero_jid, "text": MSG_BOAS_VINDAS}, headers={"apikey": EVO_KEY})
                return "OK", 200

            # --- RESPOSTA IA COM MEMÓRIA DE LONGO PRAZO ---
            prompt_sistema = (
                "Você é o Coach Max, um personal trainer e nutricionista focado em resultados. "
                "Sua missão é memorizar NOME, PESO, ALTURA e IDADE do aluno. "
                "Sempre que o aluno falar que perdeu ou ganhou peso, consulte o peso anterior no histórico e faça o cálculo para ele. "
                "Seja motivador e use os dados dele para personalizar as dicas. "
                f"Status atual: O aluno tem {dias} dias de assinatura."
            )

            mensagens_ia = [{"role": "system", "content": prompt_sistema}]
            mensagens_ia.extend(historico)
            mensagens_ia.append({"role": "user", "content": texto})

            res_ai = requests.post("https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-3.5-turbo", "messages": mensagens_ia, "temperature": 0.7},
                headers={"Authorization": f"Bearer {OPENAI_KEY}"}, timeout=25
            )
            resposta_ia = res_ai.json()['choices'][0]['message']['content']
            
            gerenciar_memoria(numero_jid, texto, resposta_ia)
            requests.post(f"{EVO_URL}/message/sendText/{INSTANCIA}", json={"number": numero_jid, "text": resposta_ia}, headers={"apikey": EVO_KEY})

        except Exception as e:
            log_print(f"Erro: {e}")
    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))