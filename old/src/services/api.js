// services/api.js
import axios from 'axios';

// Criar instância do axios com a URL base do backend
const api = axios.create({
    baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api',
    timeout: 10000, // 10 segundos de timeout
    headers: {
        'Content-Type': 'application/json',
    },
});

// Interceptor para log de requisições (útil para debug)
api.interceptors.request.use(
    (config) => {
        console.log(`📤 Enviando requisição para: ${config.url}`, config.data);
        return config;
    },
    (error) => {
        console.error('❌ Erro na requisição:', error);
        return Promise.reject(error);
    }
);

// Interceptor para log de respostas - sem usar any
api.interceptors.response.use(
    (response) => {
        console.log(`📥 Resposta recebida de: ${response.config.url}`, response.data);
        return response;
    },
    (error) => {
        if (error.response) {
            // O servidor respondeu com status de erro
            console.error('❌ Erro na resposta:', error.response.data);
        } else if (error.request) {
            // A requisição foi feita mas não houve resposta
            console.error('❌ Sem resposta do servidor');
        } else {
            // Erro na configuração da requisição
            console.error('❌ Erro na requisição:', error.message);
        }
        return Promise.reject(error);
    }
);

export default api;