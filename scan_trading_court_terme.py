import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

EMAIL_EXPEDITEUR = os.getenv("EMAIL_EXPEDITEUR")
EMAIL_MDP = os.getenv("EMAIL_MDP")
EMAIL_DESTINATAIRE = os.getenv("EMAIL_DESTINATAIRE")

# Envoi test
msg = MIMEText("🚀 Ceci est un test d'envoi automatique via Render.com")
msg['Subject'] = "📈 Alerte de test Render"
msg['From'] = EMAIL_EXPEDITEUR
msg['To'] = EMAIL_DESTINATAIRE

try:
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_EXPEDITEUR, EMAIL_MDP)
        server.send_message(msg)
        print("✅ Email envoyé avec succès.")
except Exception as e:
    print(f"❌ Erreur d'envoi : {e}")
