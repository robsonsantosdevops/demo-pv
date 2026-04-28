// services/api.js
import axios from 'axios';

// URL base: pode ser definida em runtime via setApiBaseURL() (chamado pelo ApmRumProvider após /api/config)
let apiBaseURL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api';

const api = axios.create({
    baseURL: apiBaseURL,
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json',
    },
});

/** Define a URL base da API em runtime (para K8s/ingress e para o RUM propagar trace ao backend correto). */
export function setApiBaseURL(url) {
    if (url) {
        apiBaseURL = url;
        api.defaults.baseURL = url;
    }
}

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