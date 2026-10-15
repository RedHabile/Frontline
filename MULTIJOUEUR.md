# Frontline — serveur multijoueur

Ce service fournit des salons privés avec code d'invitation (6 caractères), jusqu'à 6 joueurs, présence des joueurs et relais de messages en temps réel.

## Déploiement sur Render

1. Crée un service Web depuis le dépôt GitHub `RedHabile/Frontline`.
2. Render détecte `render.yaml`; sinon utilise `npm install` comme commande de construction et `npm start` comme commande de démarrage.
3. Une fois déployé, récupère l'URL HTTPS du service. Le client WebSocket utilisera la même adresse en remplaçant `https://` par `wss://`.

## Important

Le serveur de salons est une première brique. Le jeu actuel doit encore connecter ses actions et son moteur de simulation à ce serveur pour que les joueurs contrôlent réellement la même partie. Ne partage jamais de clé secrète dans le code public du navigateur.
