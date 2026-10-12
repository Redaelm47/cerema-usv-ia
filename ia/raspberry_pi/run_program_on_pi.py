import paramiko
import time
import socket
import argparse

# Gestion des arguments depuis ton PC (avec seuil et intervalle en plus)
parser = argparse.ArgumentParser(description="Lance un script à distance sur le Raspberry Pi")
parser.add_argument('--script', type=str, default='yolo_json_export.py', help='Nom du script Python à exécuter sur le Pi')
parser.add_argument('--model', type=str, default='best.pt', help='Nom du modèle à utiliser (ex: best.pt)')
parser.add_argument('--thresh', type=float, default=0.5, help='Seuil de confiance minimal')
parser.add_argument('--interval', type=float, default=1.0, help='Temps en secondes entre 2 enregistrements')
args = parser.parse_args()

hostname = "cerema-pi.local"
username = "pi"
password = "cerema"

# Construction dynamique de la commande avec le seuil et l'intervalle
if args.script == 'yolo_json_export.py':
    command = f"cd Desktop/Yolo_test && source yolo_env/bin/activate && python {args.script} --model {args.model} --thresh {args.thresh} --interval {args.interval}"
elif args.script == 'yolo_detect_rasp.py':
    command = f"cd Desktop/Yolo_test && source yolo_env/bin/activate && python {args.script} --model {args.model} --source picamera0 --resolution 640x480 --record --no-display"
else:
    command = f"cd Desktop/Yolo_test && source yolo_env/bin/activate && python {args.script} --model {args.model}"

def check_host(host, port=22, timeout=3):
    """Vérifie si le port SSH (22) du Pi répond sur le réseau."""
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.close()
        return True
    except socket.error:
        return False

print(f"En attente de connexion avec le Raspberry Pi pour lancer '{args.script}'...")

# Boucle d'attente du réseau
while not check_host(hostname):
    time.sleep(5)

print("Raspberry Pi détecté ! Connexion SSH en cours...")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname, username=username, password=password)

    print(f"Exécution distante : {command}")
    stdin, stdout, stderr = ssh.exec_command(command)

    # Affiche les retours du programme du Pi en temps réel dans ton terminal PC
    for line in iter(stdout.readline, ""):
        print(line, end="")

    ssh.close()
except Exception as e:
    print(f"Erreur de connexion : {e}")