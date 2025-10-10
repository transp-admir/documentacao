from app import create_app

app = create_app()

if __name__ == '__main__':
    # O host '0.0.0.0' torna o servidor acessível na rede local.
    # A porta 8080 é comumente usada para desenvolvimento web.
    app.run(host='0.0.0.0', port=8080, debug=True)
