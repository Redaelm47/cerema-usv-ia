import paramiko
import time
import sys
import argparse

# Récupération de ta ligne de commande exacte
parser = argparse.ArgumentParser(description="Pilotage distant de l'acquisition YOLO sur Raspberry Pi")
parser.add_argument('--script', type=str, default='yolo_json_export.py', help='Nom du script Python')
parser.add_argument('--model', type=str, default='best.pt', help='Chemin vers le modèle YOLO')
parser.add_argument('--thresh', type=float, default=0.5, help='Seuil de confiance minimal')
parser.add_argument('--interval', type=float, default=1.0, help='Intervalle d\'enregistrement en secondes')
args = parser.parse_args()

hostname = "cerema-pi.local"
username = "pi"
password = "cerema"
remote_dir = "Desktop/Yolo_test"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

print(f"Connexion au Raspberry Pi ({hostname})...")
try:
    ssh.connect(hostname, username=username, password=password)
except Exception as e:
    print(f"Erreur de connexion SSH : {e}")
    sys.exit(1)

# 1. Vide automatiquement le fichier detections.json sur le Pi pour repartir sur du propre
print("Réinitialisation du fichier detections.json sur le Pi...")
ssh.exec_command(f"cd {remote_dir} && > detections.json")

# 2. Construit la commande distante avec tes arguments
command = f"cd {remote_dir} && source yolo_env/bin/activate && python {args.script} --model {args.model} --thresh {args.thresh} --interval {args.interval}"

print(f"Lancement de l'acquisition à distance (Modèle: {args.model}, Seuil: {args.thresh}, Intervalle: {args.interval}s)...")
print("Appuie sur Ctrl+C sur ton PC pour stopper et récupérer le JSON.\n")

# Ouvre un canal interactif pour voir les logs en direct
transport = ssh.get_transport()
channel = transport.open_session()
channel.get_pty()
channel.exec_command(command)

try:
    while True:
        if channel.recv_ready():
            output = channel.recv(1024).decode('utf-8', errors='ignore')
            print(output, end="")
        if channel.exit_status_ready():
            break
        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nInterruption détectée depuis le PC. Arrêt du programme sur le Pi...")
    channel.send('\x03') # Envoie Ctrl+C à distance
    time.sleep(1)

# 3. Rapatrie automatiquement le fichier detections.json sur ton PC à la fin
print("\nTéléchargement automatique de detections.json vers ton PC...")
sftp = ssh.open_sftp()
remote_file = f"{remote_dir}/detections.json"
local_file = "detections.json"

try:
    sftp.get(remote_file, local_file)
    print("Fichier 'detections.json' récupéré avec succès dans ton dossier local !")
except Exception as e:
    print(f"Erreur lors du téléchargement du fichier : {e}")

sftp.close()
ssh.close()
print("Session terminée proprement.")