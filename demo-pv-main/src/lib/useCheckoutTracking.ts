// src/lib/useCheckoutTracking.ts
// Hook para rastrear o funil de checkout no frontend via RUM
// Usa window.elasticApm diretamente — evita criar segunda instância do agente

type CheckoutStep = 'dados_pessoais' | 'pagamento' | 'confirmacao' | 'concluido';

export function useCheckoutTracking() {

    const trackStep = (step: CheckoutStep, metadata?: Record<string, unknown>) => {
        if (typeof window === 'undefined') return;
        
        const apm = (window as any).elasticApm;
        if (!apm) return;

        const tx = apm.startTransaction(`checkout:${step}`, 'user-interaction');

        if (tx) {
            if (metadata) {
                apm.setCustomContext(metadata);
            }
            tx.end();
        }
    };

    const trackError = (step: CheckoutStep, error: Error) => {
        if (typeof window === 'undefined') return;

        const apm = (window as any).elasticApm;
        if (!apm) return;

        apm.setCustomContext({ checkout_step: step });
        apm.captureError(error);
    };

    return { trackStep, trackError };
}