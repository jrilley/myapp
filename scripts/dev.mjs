#!/usr/bin/env node
/**
 * Запускає бекенд (FastAPI + Telegram-бот) і фронтенд (CRA) однією командою.
 *
 * Чому окремий скрипт, а не concurrently: шлях до venv різний на Windows
 * (.venv\Scripts) і на Unix (.venv/bin), а ще треба зрозуміло сказати, чого
 * саме бракує, якщо оточення не піднято. Зайвої залежності теж не додаємо.
 */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const backendDir = path.join(root, 'backend');
const isWindows = process.platform === 'win32';

// --test піднімає повністю окремий інстанс: інший бот, інша група, інша БД,
// інші порти. Робочий бот при цьому може спокійно працювати паралельно.
const isTest = process.argv.includes('--test');
const APP_ENV = isTest ? 'test' : '';
const envFile = isTest ? '.env.test' : '.env';

const API_PORT = process.env.API_PORT || (isTest ? '8001' : '8000');
const WEB_PORT = process.env.PORT || (isTest ? '3001' : '3000');

const venvBin = path.join(backendDir, '.venv', isWindows ? 'Scripts' : 'bin');
const uvicorn = path.join(venvBin, isWindows ? 'uvicorn.exe' : 'uvicorn');
const reactScripts = path.join(
    root, 'node_modules', '.bin', isWindows ? 'react-scripts.cmd' : 'react-scripts'
);

const c = {
    reset: '\x1b[0m', dim: '\x1b[2m', red: '\x1b[31m',
    green: '\x1b[32m', yellow: '\x1b[33m', cyan: '\x1b[36m'
};

const fail = (message, hint) => {
    console.error(`${c.red}✖ ${message}${c.reset}`);
    if (hint) console.error(`${c.dim}${hint}${c.reset}`);
    process.exit(1);
};

// --- Перевірки перед стартом: краще одне зрозуміле повідомлення, ніж стектрейс.
if (!existsSync(uvicorn)) {
    fail(
        'Не знайдено venv бекенду.',
        isWindows
            ? 'cd backend\npython -m venv .venv\n.venv\\Scripts\\python.exe -m pip install -r requirements.txt'
            : 'cd backend\npython3 -m venv .venv\n.venv/bin/pip install -r requirements.txt'
    );
}

if (!existsSync(reactScripts)) {
    fail('Не встановлені npm-залежності.', isWindows ? 'npm.cmd install' : 'npm install');
}

if (!existsSync(path.join(backendDir, envFile))) {
    console.warn(
        `${c.yellow}⚠ backend/${envFile} не знайдено — бот не запуститься, працюватиме лише API.${c.reset}\n` +
        `${c.dim}  Створіть його з backend/${envFile}.example${c.reset}`
    );
}

// --- Запуск
const children = [];
let shuttingDown = false;

const start = (name, color, command, args, cwd, extraEnv = {}) => {
    const child = spawn(command, args, {
        cwd,
        // Windows вимагає shell для .cmd/.exe-обгорток. Це cmd.exe, а не
        // PowerShell, тому політика виконання скриптів тут ні до чого.
        shell: isWindows,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, ...extraEnv }
    });

    const prefix = `${color}[${name}]${c.reset} `;
    const pipe = (stream, target) => {
        let buffer = '';
        stream.on('data', (chunk) => {
            buffer += chunk.toString();
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) target.write(prefix + line + '\n');
        });
    };
    pipe(child.stdout, process.stdout);
    pipe(child.stderr, process.stderr);

    child.on('exit', (code) => {
        if (shuttingDown) return;
        console.log(`${prefix}${c.dim}процес завершився (код ${code})${c.reset}`);
        shutdown(code ?? 0);
    });

    children.push(child);
    return child;
};

function shutdown(code) {
    if (shuttingDown) return;
    shuttingDown = true;
    for (const child of children) {
        if (child.exitCode === null) {
            // На Windows дерево процесів не вбивається сигналом — гасимо через taskkill.
            if (isWindows) {
                spawn('taskkill', ['/pid', String(child.pid), '/f', '/t'], { stdio: 'ignore' });
            } else {
                child.kill('SIGTERM');
            }
        }
    }
    setTimeout(() => process.exit(code), 300);
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

const banner = isTest
    ? `${c.yellow}▸ ТЕСТОВИЙ інстанс${c.reset} ${c.dim}(окремий бот, окрема група, окрема БД)${c.reset}`
    : `${c.green}▸ РОБОЧИЙ інстанс${c.reset}`;

console.log(
    `${banner}\n` +
    `${c.green}▸ API${c.reset}  http://localhost:${API_PORT}  ${c.dim}(докс: /docs, конфіг: backend/${envFile})${c.reset}\n` +
    `${c.green}▸ Сайт${c.reset} http://localhost:${WEB_PORT}/applications\n` +
    `${c.dim}Ctrl+C зупиняє обидва процеси.${c.reset}\n`
);

start(
    'api', c.cyan, uvicorn,
    ['app.main:app', '--reload', '--port', API_PORT], backendDir,
    { APP_ENV }
);
start(
    'web', c.green, reactScripts, ['start'], root,
    {
        PORT: WEB_PORT,
        // Проксі в package.json жорстко вказує на :8000, тому тестовий сайт
        // має ходити в API за абсолютним URL. api.js читає саме цю змінну.
        ...(isTest ? { REACT_APP_API_URL: `http://localhost:${API_PORT}/api` } : {})
    }
);
