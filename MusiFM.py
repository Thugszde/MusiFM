import json
import os
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import time
from datetime import datetime, timedelta
import random
from collections import defaultdict
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, CallbackContext

# Carrega variáveis de ambiente do arquivo .env (API_KEY do Last.fm e TOKEN do Telegram)
load_dotenv()
API_KEY = os.getenv('1189f1520ff9b025cc1d6bfefa43035e')  
TOKEN = ('7682007615:AAFbMtdjSYURvmRpLEAFNlhnDccGR2Pfh4k')  # Certifique-se de que este é o nome correto da variável no .env

# Dicionário para armazenar as sessões dos usuários (user_id -> lastfm_username)
user_sessions = {}

# Função para fazer requests para a API do Last.fm
def lastfm_api_request(method, params):
    base_url = "http://ws.audioscrobbler.com/2.0/?method=user.getinfo&user=<username>&api_key=a8888950681b58caa8a056509dd769a5&format=json"
    params['api_key'] = API_KEY
    params['format'] = 'json'
    
    response = requests.get(base_url, params=params)
    return response.json()

# Dicionário para armazenar o ranking dos jogadores
ranking = defaultdict(int)

# Dicionário para armazenar os dados do jogo em grupo
current_game = None  # Armazena os dados do jogo atual para o grupo

async def start_trivia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_game
    chat_id = update.effective_chat.id
    
    # Verifica se já existe um jogo em andamento
    if current_game:
        await update.message.reply_text("Um jogo de trivia já está em andamento. Use /mskip para pular ou /mranking para ver o ranking.")
        return
    
    # Busca as faixas populares do Last.fm
    params = {
        'method': 'chart.gettoptracks',
        'limit': 10  # Limita a 10 faixas
    }
    response = lastfm_api_request('chart.gettoptracks', params)
    
    if not response.get('tracks'):
        await update.message.reply_text("Não foi possível obter faixas populares. Tente novamente.")
        return

    # Armazena a música atual e as faixas para adivinhar
    tracks = response['tracks']['track']
    selected_track = random.choice(tracks)

    current_game = {
        'track': selected_track,
        'attempts': 0,
        'correct': False,
        'hint_index': 0,  # Índice para controlar a letra que será revelada
        'players': set()  # Conjunto para armazenar jogadores que adivinhou
    }
    
    # Cria uma string com a música em asteriscos
    masked_title = '*' * len(selected_track['name'])
    
    # Envia a mensagem com a música mascarada
    await update.message.reply_text(f"Adivinhe a música: {masked_title}\n")

async def provide_hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_game  # Declare como global aqui
    user_id = update.effective_user.id
    
    # Verifica se há um jogo em andamento
    if not current_game:
        await update.message.reply_text("Não há um jogo de trivia em andamento. Use /mtrivia para começar.")
        return

    track_name = current_game['track']['name']
    hint_index = current_game['hint_index']

    # Revela a próxima letra na música
    if hint_index < len(track_name):
        hint = track_name[:hint_index + 1] + '*' * (len(track_name) - hint_index - 1)
        current_game['hint_index'] += 1  # Atualiza o índice da letra a ser revelada
    else:
        hint = "Todas as letras foram reveladas!"

    await update.message.reply_text(hint)

async def skip_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_game  # Declare como global aqui
    # Verifica se há um jogo em andamento
    if not current_game:
        await update.message.reply_text("Não há um jogo de trivia em andamento. Use /mtrivia para começar.")
        return

    # Pula para a próxima música
    current_game = None  # Remove o jogo atual
    await start_trivia(update, context)

async def guess_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_game  # Declare como global aqui
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Verifica se há um jogo em andamento
    if not current_game:
        await update.message.reply_text("Não há um jogo de trivia em andamento. Use /mtrivia para começar.")
        return

    guess = ' '.join(context.args).strip().lower()  # Obtém o palpite do usuário
    track_name = current_game['track']['name']

    # Verifica se o palpite está correto
    if guess == track_name.lower():
        ranking[user_id] += 1  # Incrementa o ranking do usuário
        current_game['players'].add(user_name)  # Adiciona o usuário que adivinhou
        await update.message.reply_text(f"Parabéns, {user_name}! Você adivinhou corretamente: {track_name}! 🎉")
        
        # Verifica se todos os jogadores já adivinharam
        if len(current_game['players']) == len(update.effective_chat.members):
            await update.message.reply_text("Todos os jogadores adivinharem, o jogo terminou!")
            current_game = None  # Termina o jogo
        else:
            await update.message.reply_text("Continue tentando, outros jogadores ainda podem adivinhar!")
    else:
        await update.message.reply_text(f"Incorreto, {user_name}. Tente novamente ou use /mdica para uma dica.")

async def show_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ranking:
        await update.message.reply_text("Ainda não há jogadores no ranking.")
        return

    # Cria uma mensagem de ranking
    ranking_message = "🏆 Ranking de Adivinhações 🏆\n"
    for user_id, score in ranking.items():
        user = await context.bot.get_chat(user_id)
        ranking_message += f"{user.first_name}: {score}\n"

    await update.message.reply_text(ranking_message)

# Dicionários para armazenar os cartões, sessões de usuários e contagens de cartões
cards = {}
user_sessions = {}  # Dicionário para armazenar sessões de usuários
authorized_users = {6575077497}  # Conjunto de IDs de usuários autorizados
user_card_counts = {}  # Contagem de cartões dos usuários

# Função para carregar os cartões e as contagens de cartões
def load_data():
    try:
        with open("data.json", "r") as file:
            data = json.load(file)
            return data.get("cards", {}), data.get("user_card_counts", {})
    except FileNotFoundError:
        return {}, {}  # Retorna dicionários vazios se o arquivo não existir

# Função para salvar os cartões e as contagens de cartões
def save_cards():
    with open("data.json", "w") as file:
        json.dump({"cards": cards, "user_card_counts": user_card_counts}, file)

# Carregar dados ao iniciar o bot
cards, user_card_counts = load_data()

# Função para verificar se o usuário é autorizado
def is_authorized(user_id):
    return user_id in authorized_users

# Função para adicionar um novo cartão (/addcard <id> <raridade> <nome>)
async def add_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Você não tem permissão para usar este comando.")
        return

    if len(context.args) < 3:
        await update.message.reply_text("Uso correto: /addcard <id> <raridade> <nome>")
        return

    card_id = context.args[0]
    rarity = context.args[1]
    name = ' '.join(context.args[2:])  # O nome pode conter espaços

    # Adiciona o cartão ao dicionário
    cards[card_id] = {
        'rarity': rarity,
        'name': name,
        'units': 1,  # Inicia com 1 unidade
        'scrobbles': 0,  # Inicializa com 0 scrobbles
        'user_id': user_id,  # Armazena o id do usuário que adicionou o card
    }

    # Salva os cartões no arquivo JSON
    save_cards()

    await update.message.reply_text(f"Cartão adicionado: {name} ({rarity}) com ID {card_id}.")

# Função para adicionar imagem ao cartão (/setimage <id> <link>)
async def set_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Verifica se a sintaxe do comando está correta
    if len(context.args) != 2:
        await update.message.reply_text("Uso correto: /setimage <id do card> <link do imgur>")
        return

    card_id = context.args[0]
    image_url = context.args[1]

    # Verifica se o cartão existe
    if card_id not in cards:
        await update.message.reply_text(f"Cartão com ID {card_id} não encontrado.")
        return

    # Define a imagem para o cartão
    cards[card_id]["image"] = image_url

    # Mensagem de confirmação
    await update.message.reply_text(f"Imagem para o cartão {card_id} foi definida com sucesso!")

# Dicionários para armazenar dados do jogador
player_spins = {}  # Giros restantes por jogador
player_last_spin_time = {}  # Última vez que o jogador fez um giro

# Quantidade máxima de giros diários
MAX_SPINS = 24
SPIN_RECOVERY_TIME = timedelta(hours=2)  # Tempo de recuperação de giros (2 horas)
SPINS_RECOVERY_AMOUNT = 2  # Quantidade de giros que recupera a cada 2 horas

# Função para carregar dados do jogador (giros e tempos)
def load_player_data():
    try:
        with open("player_data.json", "r") as file:
            data = json.load(file)
            return data.get("player_spins", {}), data.get("player_last_spin_time", {})
    except FileNotFoundError:
        return {}, {}

# Função para salvar dados do jogador (giros e tempos)
def save_player_data():
    with open("player_data.json", "w") as file:
        json.dump({
            "player_spins": player_spins,
            "player_last_spin_time": {key: value.timestamp() for key, value in player_last_spin_time.items()}
        }, file)

# Carregar dados ao iniciar o bot
player_spins, last_spin_times_timestamps = load_player_data()
# Converter timestamps para objetos datetime
player_last_spin_time = {key: datetime.fromtimestamp(value) for key, value in last_spin_times_timestamps.items()}

# Função para verificar e restaurar giros do jogador
def restore_spins(user_id):
    now = datetime.now()
    if user_id not in player_last_spin_time:
        player_last_spin_time[user_id] = now  # Inicializa o tempo se for a primeira vez

    last_spin_time = player_last_spin_time[user_id]
    elapsed_time = now - last_spin_time

    # Calcula quantos períodos de recuperação se passaram (2 horas = SPIN_RECOVERY_TIME)
    recovery_periods = elapsed_time // SPIN_RECOVERY_TIME
    if recovery_periods >= 1:
        player_spins[user_id] = min(MAX_SPINS, player_spins.get(user_id, MAX_SPINS) + (recovery_periods * SPINS_RECOVERY_AMOUNT))
        player_last_spin_time[user_id] = now  # Atualiza o último tempo de spin
        save_player_data()  # Salva após restaurar giros

# Variáveis globais (você deve substituir essas por sua lógica de armazenamento)
MAX_SPINS = 24  # Total de giros disponíveis
player_spins = {}  # Dicionário para armazenar giros de cada usuário

# Função para restaurar giros (adapte conforme sua lógica)
def restore_spins(user_id):
    if user_id not in player_spins:
        player_spins[user_id] = MAX_SPINS  # Restaurar giros se o jogador não estiver no dicionário

# Função de comando /musi
async def musi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Restaura giros do jogador se for possível
    restore_spins(user_id)

    # Verifica quantos giros o jogador ainda tem
    spins_left = player_spins.get(user_id, MAX_SPINS)

    # Mensagem inicial
    welcome_message = f"Bem-vindo ao MusiFm 📀 {update.effective_user.first_name}!\n"
    welcome_message += f"Você tem {spins_left} de {MAX_SPINS} giros restantes."

    # Criação do botão inline para o comando /musi
    keyboard = [[InlineKeyboardButton("📀 Girar", callback_data="musi_spin")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_message, reply_markup=reply_markup)

# Função que lida com o clique do botão para o comando /musi
async def musi_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)

    # Verifica quantos giros o jogador ainda tem
    spins_left = player_spins.get(user_id, MAX_SPINS)

    if spins_left <= 0:
        await context.bot.send_message(chat_id=query.message.chat_id, text="Você não tem mais giros disponíveis. Aguarde 2 horas para ganhar mais 2 giros.")
        return

    # Remove um giro
    player_spins[user_id] = spins_left - 1
    save_player_data()  # Salva após o giro

    # Remove a mensagem original com o botão
    await query.message.delete()

    # Seleciona um cartão aleatório baseado nas probabilidades
    card_id = choose_card()  # Função que escolhe um card com base nas probabilidades
    if card_id is None:
        await context.bot.send_message(chat_id=query.message.chat_id, text="Nenhum cartão disponível. Adicione cartões usando /addcard.")
        return

    card = cards[card_id]

    # Adiciona o card à mochila do jogador
    if user_id not in user_card_counts:
        user_card_counts[user_id] = {}  # Cria o dicionário se o jogador não tiver cards ainda

    # Incrementa a quantidade ou inicializa com 1
    if card_id in user_card_counts[user_id]:
        user_card_counts[user_id][card_id] += 1
    else:
        user_card_counts[user_id][card_id] = 1

    # Salva as contagens de cartões no JSON
    save_cards()

    # Mensagem ao girar o card
    message = f"📀 Nós ouvimos e te entregamos:\n"
    message += f"\n"
    message += f"👨‍🎤 {card_id}. {card['rarity']} {card['name']}\n"
    message += f"\n"
    message += f"💃 {update.effective_user.first_name} {user_card_counts[user_id][card_id]}x unidades"

    # Envia a mensagem com o card girado e a imagem
    if 'image' in card:
        await context.bot.send_photo(chat_id=query.message.chat_id, photo=card['image'], caption=message)
    else:
        await context.bot.send_message(chat_id=query.message.chat_id, text=message)

# Função que escolhe um card com base nas probabilidades
def choose_card():
    roll = random.randint(1, 100)
    if roll <= 20:  # 20% de chance para 🥇
        rarity = "🥇"
    elif roll <= 70:  # 50% de chance para 🥈 (20% + 50% = 70%)
        rarity = "🥈"
    else:  # 30% de chance para 🥉
        rarity = "🥉"
    
    # Filtra os cards disponíveis com a raridade escolhida
    available_cards = [card_id for card_id, card in cards.items() if card['rarity'] == rarity]
    
    if available_cards:
        return random.choice(available_cards)
    return None

# Função para exibir a mochila do jogador
async def mochila(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Verifica se o usuário possui cartões
    if user_id in user_card_counts and user_card_counts[user_id]:
        message = "🎒 Sua Mochila:\n"
        for card_id, count in user_card_counts[user_id].items():
            card = cards.get(card_id, {})
            rarity = card.get('rarity', 'Desconhecida')
            name = card.get('name', 'Desconhecido')
            message += f"👨‍🎤 ID: {card_id} | Raridade: {rarity} | Nome: {name} | Quantidade: {count}x\n"
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("Você não possui cartões na mochila.")

# Função para visualizar detalhes de um cartão específico
async def view_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)  # Converte o ID do usuário para string
    if len(context.args) != 1:
        await update.message.reply_text("Uso correto: /carta <id>")
        return

    card_id = context.args[0]

    # Verifica se o cartão existe
    card = cards.get(card_id)
    if not card:
        await update.message.reply_text(f"Cartão com ID {card_id} não encontrado.")
        return

    # Verifica se o usuário possui esse cartão
    count = user_card_counts.get(user_id, {}).get(card_id, 0)

    # Define o emoji baseado na quantidade
    if count >= 200:
        emoji = "🏆"
    elif count >= 150:
        emoji = "☀️"
    elif count >= 100:
        emoji = "🪐"
    elif count >= 50:
        emoji = "🌟"
    elif count >= 40:
        emoji = "🌠"
    elif count >= 30:
        emoji = "⭐"
    elif count >= 20:
        emoji = "💫"
    elif count >= 10:
        emoji = "✨"
    else:
        emoji = ""  # Nenhum emoji se a contagem for menor que 10

    # Mensagem detalhada do cartão
    message = f"👨‍🎤 {card_id}. {card['rarity']} {card['name']} {emoji}\n"
    message += f"💼 {count}x unidades \n"
    message += f"\n"
    message += f"💃 {update.effective_user.first_name}\n" 

    # Envia a mensagem com a imagem, se existir
    if 'image' in card:
        await update.message.reply_photo(card['image'], caption=message)
    else:
        await update.message.reply_text(message)

# Dicionário para armazenar o estado da página atual de cada usuário
user_pages = {}

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# Função para listar todos os cartões disponíveis (/lista)
async def list_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verifica se há cartões disponíveis
    if not cards:
        await update.message.reply_text("Nenhum cartão disponível no momento.")
        return

    # Preparar a mensagem com a lista de cartões
    message = "📋 Lista de Cartões Disponíveis:\n"
    for card_id, card in cards.items():
        message += f"ID: {card_id} | Nome: {card['name']} | Raridade: {card['rarity']}\n"

    # Enviar a mensagem com a lista de cartões
    await update.message.reply_text(message)

# Função para carregar perfis de jogadores
def load_profiles():
    try:
        with open("profiles.json", "r") as file:
            content = file.read().strip()
            if not content:
                return {}
            return json.loads(content)  # Tenta carregar o JSON
    except FileNotFoundError:
        return {}  # Retorna dicionário vazio se o arquivo não existir
    except json.JSONDecodeError:
        print("Erro ao decodificar o JSON. Criando um novo arquivo.")
        return {}  # Retorna dicionário vazio se o JSON estiver malformado

# Função para salvar perfis de jogadores
def save_profiles():
    with open("profiles.json", "w") as file:
        json.dump(player_profiles, file)

# Carregar perfis ao iniciar o bot
player_profiles = load_profiles()

# Função para o comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name

    # Verifica se o jogador já tem um perfil
    if user_id not in player_profiles:
        # Criar perfil do jogador
        player_profiles[user_id] = {
            'name': user_name,
            'coins': 0,
            'bio': '',
            'favorite_card': None
        }
        save_profiles()  # Salva o perfil após a criação

        # Mensagem de boas-vindas
        message = f"Bem-vindo, {user_name}!\nSeu perfil foi criado com sucesso! 🎮"
    else:
        message = f"Bem-vindo de volta, {user_name}!"

    message += "\nUse o comando /girar para começar a jogar e ganhar cartas!"
    await update.message.reply_text(message)

async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # Verifica se o perfil do jogador existe
    if user_id not in player_profiles:
        await update.message.reply_text("Você não tem um perfil ainda.")
        return

    profile = player_profiles[user_id]
    favorite_card_id = profile.get("favorite_card")

    # Mensagem inicial do perfil
    message = f"🎮 Seu Perfil: {update.effective_user.first_name}\n"
    message += f"💰 Moedas: {profile.get('coins', 0)}\n"
    
    # Exibe a contagem de cartas, somando a quantidade de cada carta que o jogador possui
    total_cards = sum(user_card_counts.get(user_id, {}).values())
    message += f"📦 Cartas: {total_cards}\n"  # Exibe a contagem total de cartas
    message += f"📜 Biografia: {profile.get('bio', 'Você ainda não definiu uma biografia.')}\n"  # Exibe a biografia

    # Exibir o cartão favorito se existir
    if favorite_card_id and favorite_card_id in cards:
        favorite_card = cards[favorite_card_id]
        message += f"🌟 Cartão Favorito: {favorite_card['name']}\n"
        if 'image' in favorite_card:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=favorite_card['image'], caption=message)
        else:
            await update.message.reply_text(message)
    else:
        message += "🌟 Você não tem um cartão favorito.\n"
        await update.message.reply_text(message)


# Função para definir a biografia do jogador
async def bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if len(context.args) == 0:
        await update.message.reply_text("Por favor, forneça uma biografia. Exemplo: /bio Sua biografia aqui.")
        return

    # Junta todos os argumentos para formar a biografia
    new_bio = ' '.join(context.args)
    
    # Atualiza a biografia no perfil do jogador
    if user_id not in player_profiles:
        player_profiles[user_id] = {}  # Cria o perfil se não existir
    player_profiles[user_id]['bio'] = new_bio

    # Salva as alterações no perfil
    save_profiles()

    await update.message.reply_text(f"Sua biografia foi atualizada para: {new_bio}")

# Função para definir um cartão como favorito
async def fav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if len(context.args) != 1:
        await update.message.reply_text("Uso correto: /fav <id do cartão>")
        return

    card_id = context.args[0]
    if card_id not in cards:
        await update.message.reply_text("Esse cartão não existe.")
        return

    # Adiciona o cartão favorito ao perfil do jogador
    if user_id not in player_profiles:
        player_profiles[user_id] = {"favorite_card": None}

    player_profiles[user_id]["favorite_card"] = card_id
    save_profiles()  # Salva os perfis atualizados

    await update.message.reply_text(f"Você agora favoritou o cartão {card_id}!")

    # Função para doar cartas a outro jogador
async def doar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Uso correto: /doar <id_do_card1> <id_do_card2> ...")
        return
    
    # ID do usuário que está doando
    donor_id = str(update.effective_user.id)
    recipient_id = str(update.message.reply_to_message.from_user.id)

    # Verifica se o jogador está doando a si mesmo
    if donor_id == recipient_id:
        await update.message.reply_text("Você não pode doar cartas para si mesmo.")
        return

    # Verifica se o jogador tem os cartões que está tentando doar
    donated_cards = context.args
    user_cards = user_card_counts.get(donor_id, {})
    
    # Verifica se o jogador possui todos os cartões
    for card_id in donated_cards:
        if card_id not in user_cards or user_cards[card_id] <= 0:
            await update.message.reply_text(f"Você não possui o cartão com ID {card_id}.")
            return
    
    # Doar os cartões
    for card_id in donated_cards:
        user_cards[card_id] -= 1  # Remove uma unidade do cartão do doador
        # Adiciona o cartão ao receptor
        if card_id not in user_card_counts.get(recipient_id, {}):
            user_card_counts.setdefault(recipient_id, {})[card_id] = 0
        user_card_counts[recipient_id][card_id] += 1  # Adiciona uma unidade ao receptor

    save_cards()
    await update.message.reply_text(f"Você doou os cartões com IDs: {', '.join(donated_cards)} para {recipient_id}.")

# Função para comprar giros
async def comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    profile = player_profiles.get(user_id, {})
    coins = profile.get('coins', 0)

    # Preço de cada giro
    price_per_spin = 1000

    if coins < price_per_spin:
        await update.message.reply_text(f"Você não tem moedas suficientes. Você precisa de {price_per_spin} moedas para comprar 1 giro.")
        return

    # Deduz as moedas e adiciona um giro
    profile['coins'] -= price_per_spin
    player_spins[user_id] = player_spins.get(user_id, MAX_SPINS) + 1  # Adiciona um giro

    save_profiles()
    await update.message.reply_text(f"Você comprou 1 giro! Moedas restantes: {profile['coins']}.")

# Função para vender cartas
async def vender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Uso correto: /vender <id_do_card1> <id_do_card2> ...")
        return
    
    user_id = str(update.effective_user.id)
    user_cards = user_card_counts.get(user_id, {})

    # Dicionário de preços por raridade
    rarity_prices = {
        'ouro': 1000,
        'prata': 500,
        'bronze': 250,
    }

    total_coins = 0

    # Verifica se o jogador possui todos os cartões que está tentando vender
    for card_id in context.args:
        if card_id in user_cards and user_cards[card_id] > 0:
            card = cards.get(card_id, {})
            rarity = card.get('rarity', 'desconhecida').lower()
            total_coins += rarity_prices.get(rarity, 0)
            user_cards[card_id] -= 1  # Remove uma unidade do cartão vendido
        else:
            await update.message.reply_text(f"Você não possui o cartão com ID {card_id}.")
            return

    if total_coins > 0:
        profile = player_profiles.get(user_id, {})
        profile['coins'] = profile.get('coins', 0) + total_coins  # Adiciona as moedas ganhas
        save_profiles()

        # Salva as contagens de cartões atualizadas
        save_cards()

        await update.message.reply_text(f"Você vendeu os cartões e ganhou {total_coins} moedas!")
    else:
        await update.message.reply_text("Você não vendeu nenhum cartão.")

AUTHORIZED_USER_ID = "6575077497"

        # Função para doar giros ou moedas
async def doa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Verifica se o usuário é o autorizado
    if user_id != AUTHORIZED_USER_ID:
        await update.message.reply_text("Você não está autorizado a usar este comando.")
        return

    if len(context.args) < 3:  # Verifica se existem argumentos suficientes
        await update.message.reply_text("Uso correto: /doar <tipo> <id_do_usuario|all> <quantidade>")
        return

    tipo = context.args[0].lower()  # Tipo pode ser 'giros' ou 'moedas'
    destinatario = context.args[1]  # ID do destinatário ou 'all'
    quantidade = int(context.args[2])  # Quantidade a ser doada

    # Verifica se o tipo é válido
    if tipo not in ['giros', 'moedas']:
        await update.message.reply_text("Tipo inválido. Use 'giros' ou 'moedas'.")
        return

    # Doação de giros
    if tipo == 'giros':
        if quantidade < 1:
            await update.message.reply_text("Você deve doar pelo menos 1 giro.")
            return

        if destinatario == 'all':
            # Doar giros a todos os usuários
            for uid in player_spins.keys():
                player_spins[uid] += quantidade  # Adiciona giros a todos os usuários
            await update.message.reply_text(f"Você doou {quantidade} giros para todos os jogadores.")
        else:
            # Doar giros a um usuário específico
            if destinatario in player_spins:
                player_spins[destinatario] += quantidade
                await update.message.reply_text(f"Você doou {quantidade} giros para o usuário {destinatario}.")
            else:
                await update.message.reply_text("Usuário não encontrado.")

    # Doação de moedas
    elif tipo == 'moedas':
        if quantidade < 1:
            await update.message.reply_text("Você deve doar pelo menos 1 moeda.")
            return

        if destinatario == 'all':
            # Doar moedas a todos os usuários
            for uid in player_profiles.keys():
                profile = player_profiles[uid]
                profile['coins'] = profile.get('coins', 0) + quantidade  # Adiciona moedas a todos os usuários
            await update.message.reply_text(f"Você doou {quantidade} moedas para todos os jogadores.")
        else:
            # Doar moedas a um usuário específico
            if destinatario in player_profiles:
                profile = player_profiles[destinatario]
                profile['coins'] = profile.get('coins', 0) + quantidade  # Adiciona moedas ao usuário
                await update.message.reply_text(f"Você doou {quantidade} moedas para o usuário {destinatario}.")
            else:
                await update.message.reply_text("Usuário não encontrado.")   
    await update.message.reply_text(message)


    # Salva os cartões no arquivo JSON
    save_cards()

# Função principal para iniciar o bot
def main():
    app = Application.builder().token(TOKEN).build()

    # Comandos do bot
    app.add_handler(CommandHandler("mtrivia", start_trivia))
    app.add_handler(CommandHandler("mdica", provide_hint))
    app.add_handler(CommandHandler("mskip", skip_track))
    app.add_handler(CommandHandler("mguess", guess_track))
    app.add_handler(CommandHandler("mranking", show_ranking))
    app.add_handler(CommandHandler("musi", musi))
    app.add_handler(CommandHandler("addcard", add_card))
    app.add_handler(CommandHandler("setimage", set_image))
    app.add_handler(CallbackQueryHandler(musi_button_callback, pattern='musi_spin'))
    app.add_handler(CommandHandler("mochila", mochila))
    app.add_handler(CommandHandler("carta", view_card)) 
    app.add_handler(CommandHandler("lista", list_cards))
    app.add_handler(CommandHandler("perfil", perfil))
    app.add_handler(CommandHandler("bio", bio))
    app.add_handler(CommandHandler("fav", fav))
    app.add_handler(CommandHandler("doar", doar))
    app.add_handler(CommandHandler("comprar", comprar))
    app.add_handler(CommandHandler("vender", vender))
    app.add_handler (CommandHandler("doa", doa))
    app.add_handler(CommandHandler("start", start))

    # Iniciar o bot
    app.run_polling()

if __name__ == '__main__':
    main()
