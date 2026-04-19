import requests
import base64

# Configurações da API
URL = "http://voice.manerostream.com.br/api/v1/voice-conversion" # Ajuste se o IP/Porta for diferente
OUTPUT_FILE = "resultado_audio.wav"

# Dados da conversão
payload = {
    'text': """Gente, eu preciso compartilhar uma descoberta: o Churros do Guga.Sabe aquela vontade de um doce que realmente te satisfaça? Eu mordi e não acreditei. A massa tem exatos 10cm de pura perfeição: é incrivelmente crocante por fora, firme, e quando você chega no recheio... é uma explosão de sabor!
É uma experiência completa. Você sente a textura, o açúcar com canela e aquele recheio generoso. Eu coloquei na boca e a única coisa que consegui pensar foi: 'Por que eu não pedi dois?'. Se você quer um prazer de verdade para o seu paladar, o Guga entrega tudo. É impossível comer um só!""",
    'language': 'Portuguese',
    'num_step': '5',
    'speed': '1.0'
}

# Caminho do seu áudio de referência
audio_path = r'C:\Users\PC2\Desktop\Matheus TI.wav'

try:
    with open(audio_path, 'rb') as audio_file:
        files = {
            'ref_audio': ('Gustavo.wav', audio_file, 'audio/wav')
        }
        
        print("Enviando requisição para a API...")
        response = requests.post(URL, data=payload, files=files)
        
        if response.status_code == 200:
            data = response.json()
            audio_base64 = data['audio_base64']
            
            # Decodifica o Base64 e salva em um arquivo .wav
            audio_bytes = base64.b64decode(audio_base64)
            with open(OUTPUT_FILE, 'wb') as f:
                f.write(audio_bytes)
            
            print(f"Sucesso! Áudio gerado e salvo como: {OUTPUT_FILE}")
        else:
            print(f"Erro na API ({response.status_code}): {response.text}")

except FileNotFoundError:
    print(f"Erro: O arquivo de áudio não foi encontrado no caminho: {audio_path}")
except Exception as e:
    print(f"Ocorreu um erro: {e}")
