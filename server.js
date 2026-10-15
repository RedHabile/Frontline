// Frontline multiplayer room server
// Node.js 20+; WebSocket rooms with private 6-character invite codes.
const http = require('node:http');
const crypto = require('node:crypto');
const { WebSocketServer, WebSocket } = require('ws');

const PORT = Number(process.env.PORT || 3000);
const MAX_PLAYERS = 6;
const ROOM_TTL_MS = 3 * 60 * 60 * 1000;
const rooms = new Map();

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ name: 'Frontline multiplayer', status: 'online', rooms: rooms.size }));
});
const wss = new WebSocketServer({ server, maxPayload: 64 * 1024 });

function makeCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code;
  do {
    code = Array.from({ length: 6 }, () => chars[crypto.randomInt(chars.length)]).join('');
  } while (rooms.has(code));
  return code;
}
function send(ws, obj) {
  if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}
function broadcast(room, obj, except) {
  for (const client of room.clients) if (client !== except) send(client, obj);
}
function cleanRoom(code) {
  const room = rooms.get(code);
  if (!room || room.clients.size) return;
  clearTimeout(room.timer);
  rooms.delete(code);
}
function safeName(value) {
  return String(value || 'Joueur').replace(/[<>\u0000-\u001f]/g, '').trim().slice(0, 14) || 'Joueur';
}

wss.on('connection', (ws) => {
  ws.roomCode = null;
  ws.playerId = crypto.randomUUID();
  ws.isHost = false;

  ws.on('message', (raw) => {
    let msg;
    try { msg = JSON.parse(raw.toString()); } catch { return send(ws, { type: 'error', message: 'Message invalide.' }); }
    if (!msg || typeof msg.type !== 'string') return;

    if (msg.type === 'create') {
      if (ws.roomCode) return send(ws, { type: 'error', message: 'Vous êtes déjà dans une salle.' });
      const code = makeCode();
      const room = { code, host: ws, clients: new Set([ws]), players: new Map(), createdAt: Date.now(), timer: null };
      rooms.set(code, room);
      ws.roomCode = code; ws.isHost = true;
      const player = { id: ws.playerId, name: safeName(msg.name), host: true };
      room.players.set(ws.playerId, player);
      send(ws, { type: 'room-created', code, playerId: ws.playerId, players: [...room.players.values()], maxPlayers: MAX_PLAYERS });
      return;
    }

    if (msg.type === 'join') {
      if (ws.roomCode) return send(ws, { type: 'error', message: 'Vous êtes déjà dans une salle.' });
      const code = String(msg.code || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6);
      const room = rooms.get(code);
      if (!room) return send(ws, { type: 'error', message: 'Code inconnu ou salle expirée.' });
      if (room.clients.size >= MAX_PLAYERS) return send(ws, { type: 'error', message: 'Cette salle est complète (6 joueurs maximum).' });
      if (room.started) return send(ws, { type: 'error', message: 'La partie a déjà commencé.' });
      ws.roomCode = code; ws.isHost = false;
      const player = { id: ws.playerId, name: safeName(msg.name), host: false };
      room.clients.add(ws); room.players.set(ws.playerId, player);
      send(ws, { type: 'room-joined', code, playerId: ws.playerId, players: [...room.players.values()], maxPlayers: MAX_PLAYERS });
      broadcast(room, { type: 'player-joined', player, players: [...room.players.values()] }, ws);
      return;
    }

    const room = ws.roomCode && rooms.get(ws.roomCode);
    if (!room) return send(ws, { type: 'error', message: 'Rejoignez une salle avant cette action.' });

    if (msg.type === 'start') {
      if (!ws.isHost) return send(ws, { type: 'error', message: 'Seul l’hôte peut lancer la partie.' });
      if (room.clients.size < 2) return send(ws, { type: 'error', message: 'Il faut au moins deux joueurs.' });
      room.started = true;
      const settings = {
        seed: Number.isSafeInteger(msg.seed) ? msg.seed : crypto.randomInt(1, 2147483647),
        size: ['normal', 'large', 'huge'].includes(msg.size) ? msg.size : 'normal',
        bots: Math.max(0, Math.min(20, Number.isInteger(msg.bots) ? msg.bots : 8))
      };
      broadcast(room, { type: 'game-start', settings, players: [...room.players.values()] });
      return;
    }

    // Relay gameplay commands/snapshots only to members of the same private room.
    if (msg.type === 'action' || msg.type === 'snapshot' || msg.type === 'state' || msg.type === 'chat' || msg.type === 'pause' || msg.type === 'diplomacy-offer' || msg.type === 'diplomacy-answer') {
      if (JSON.stringify(msg).length > 48 * 1024) return send(ws, { type: 'error', message: 'Message trop volumineux.' });
      if (msg.type === 'snapshot' || msg.type === 'state') {
        if (!ws.isHost) return send(ws, { type: 'error', message: 'Seul l’hôte peut envoyer l’état de la partie.' });
      }
      const payload = { ...msg, from: ws.playerId };
      broadcast(room, payload, ws);
      return;
    }
  });

  ws.on('close', () => {
    const code = ws.roomCode;
    const room = code && rooms.get(code);
    if (!room) return;
    room.clients.delete(ws);
    room.players.delete(ws.playerId);
    if (room.host === ws) {
      broadcast(room, { type: 'host-left', message: 'L’hôte a quitté la salle.' });
      for (const client of room.clients) { client.close(1000, 'Host left'); }
      room.clients.clear();
      cleanRoom(code);
    } else {
      broadcast(room, { type: 'player-left', playerId: ws.playerId, players: [...room.players.values()] });
      cleanRoom(code);
    }
  });
});

const cleanup = setInterval(() => {
  const now = Date.now();
  for (const [code, room] of rooms) {
    if (!room.clients.size || now - room.createdAt > ROOM_TTL_MS) {
      for (const client of room.clients) client.close(1000, 'Room expired');
      room.clients.clear();
      cleanRoom(code);
    }
  }
}, 60_000);
cleanup.unref();

server.listen(PORT, () => console.log('Frontline multiplayer server listening on ' + PORT));
