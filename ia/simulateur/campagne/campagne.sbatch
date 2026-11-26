#!/bin/bash
# Campagne du simulateur en tableau de tâches Slurm : 1 RTX 3080 par tâche, graine = 1000 x numéro de tâche.
#
#   EPISODES=20 DUREE=180 sbatch --array=1-4 ia/simulateur/campagne/campagne.sbatch
#   PAR_GPU=2 ...   deux instances sur le même GPU (graines 1000 k et 1000 k + 500)
#
# Variables : EPISODES (10), DUREE (180 s simulées), IMG_S (5), DETECTEUR (best4_2), PAR_GPU (1),
# CAMPAGNE (AAAA-MM-JJ_HHMM, commun aux tâches), DELAI (s, défaut calculé), ARRET_A (HH:MM, arrêt propre),
# et les chemins plus bas. Les résultats sont copiés sur le Drive toutes les 10 min (points de sauvegarde).
#SBATCH --job-name=rech_usv_campagne
#SBATCH --account=mee
#SBATCH --qos=mee_short
#SBATCH --partition=Mee_Global_GPU
#SBATCH --gres=gpu:rtx3080:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --nice=100
#SBATCH --array=1-1
#SBATCH --output=/Brain/private/r25elmek/cerema-web/campagnes/slurm/%x_%A_%a.out

set -u
DEPOT=${DEPOT:-/Brain/private/r25elmek/projets/cerema-usv-ia}
OUTILS=${OUTILS:-/Brain/private/r25elmek/cerema-web/outils}
export PYTHON_CHAINE=${PYTHON_CHAINE:-$OUTILS/venv_chaine/bin/python}
export RCLONE=${RCLONE:-/Brain/private/r25elmek/bin/rclone}
export PLAYWRIGHT_BROWSERS_PATH=${PLAYWRIGHT_BROWSERS_PATH:-$OUTILS/pw-browsers}
export YOLO_CONFIG_DIR=/Brain/private/r25elmek/home/ultralytics
export HOME=/tmp/${USER}_campagne_$SLURM_JOB_ID XDG_CACHE_HOME=/tmp/${USER}_campagne_$SLURM_JOB_ID/cache
export __GL_SHADER_DISK_CACHE=0 CUDA_CACHE_DISABLE=1
mkdir -p "$HOME"
trap 'rm -rf "$HOME"' EXIT

EPISODES=${EPISODES:-10}; DUREE=${DUREE:-180}; IMG_S=${IMG_S:-5}; DETECTEUR=${DETECTEUR:-best4_2}
PAR_GPU=${PAR_GPU:-1}
if [ -z "${CAMPAGNE:-}" ]; then  # heure de soumission : la même pour toutes les tâches du tableau
  SOUMIS=$(scontrol show job "$SLURM_JOB_ID" -o | grep -o 'SubmitTime=[^ ]*' | cut -d= -f2)
  CAMPAGNE=$(date -d "${SOUMIS:-now}" +%Y-%m-%d_%H%M)
fi
K=${SLURM_ARRAY_TASK_ID:-1}
TRAVAIL=/Brain/private/r25elmek/cerema-web/campagnes/travail/${SLURM_ARRAY_JOB_ID:-$SLURM_JOB_ID}

echo "nœud $(hostname), GPU $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader), campagne $CAMPAGNE, tâche $K"
echo "commit $(git -C "$DEPOT" rev-parse --short HEAD), $EPISODES épisodes de $DUREE s, $PAR_GPU instance(s) sur le GPU"

lancer() {  # $1 nom de la tâche, $2 graine
  "$OUTILS/venv/bin/python" "$DEPOT/ia/simulateur/campagne/lancer.py" \
    --graine "$2" --episodes "$EPISODES" --duree "$DUREE" --img-s "$IMG_S" --detecteur "$DETECTEUR" \
    --tache "$1" --campagne-nom "$CAMPAGNE" --travail "$TRAVAIL" ${DELAI:+--delai "$DELAI"} ${ARRET_A:+--arret-a "$ARRET_A"} \
    --python-chaine "$PYTHON_CHAINE" --rclone "$RCLONE"
}

lancer "$K" $((1000 * K)) &
PIDS=$!
if [ "$PAR_GPU" -ge 2 ]; then
  sleep 20  # décale les chargements
  lancer "${K}b" $((1000 * K + 500)) &
  PIDS="$PIDS $!"
fi
CODE=0
for p in $PIDS; do wait "$p" || CODE=$?; done
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
echo "fin, code $CODE"
exit $CODE
