interface CheckoutStepperProps {
    etapaAtual: 1 | 2 | 3 | 4;
}

export function CheckoutStepper({ etapaAtual }: CheckoutStepperProps) {
    const etapas = [
        { numero: 1, nome: "Dados Pessoais" },
        { numero: 2, nome: "Confirmação" },
        { numero: 3, nome: "Pagamento" },
    ];

    // Etapa 4 = sucesso, tratamos como etapa 3 concluída no stepper
    const etapaVisual = etapaAtual === 4 ? 4 : etapaAtual;

    return (
        <div className="w-full max-w-xs">
            <div className="flex items-center w-full">

                {/* Etapa 1 */}
                <div className="flex items-center" style={{ width: '80px' }}>
                    <div className={`
                        w-8 h-8 md:w-9 md:h-9 rounded-full flex items-center justify-center font-bold text-sm md:text-base mx-auto
                        ${etapaVisual === 1 ? 'bg-blue-600 text-white' : etapaVisual > 1 ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'}
                    `}>
                        {etapaVisual > 1 ? '✓' : '1'}
                    </div>
                </div>

                {/* Linha 1-2 */}
                <div className={`flex-1 h-0.5 ${etapaVisual > 1 ? 'bg-green-500' : 'bg-gray-200'}`} />

                {/* Etapa 2 */}
                <div className="flex items-center" style={{ width: '70px' }}>
                    <div className={`
                        w-8 h-8 md:w-9 md:h-9 rounded-full flex items-center justify-center font-bold text-sm md:text-base mx-auto
                        ${etapaVisual === 2 ? 'bg-blue-600 text-white' : etapaVisual > 2 ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'}
                    `}>
                        {etapaVisual > 2 ? '✓' : '2'}
                    </div>
                </div>

                {/* Linha 2-3 */}
                <div className={`flex-1 h-0.5 ${etapaVisual > 2 ? 'bg-green-500' : 'bg-gray-200'}`} />

                {/* Etapa 3 */}
                <div className="flex items-center" style={{ width: '80px' }}>
                    <div className={`
                        w-8 h-8 md:w-9 md:h-9 rounded-full flex items-center justify-center font-bold text-sm md:text-base mx-auto
                        ${etapaVisual === 3 ? 'bg-blue-600 text-white' : etapaVisual > 3 ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'}
                    `}>
                        {etapaVisual > 3 ? '✓' : '3'}
                    </div>
                </div>

            </div>

            {/* Labels */}
            <div className="flex justify-between w-full mt-2">
                <div className="text-center" style={{ width: '80px' }}>
                    <span className={`text-xs font-medium whitespace-nowrap ${etapaVisual === 1 ? 'text-blue-600' : etapaVisual > 1 ? 'text-green-500' : 'text-gray-400'}`}>
                        {etapas[0].nome}
                    </span>
                </div>
                <div className="text-center" style={{ width: '70px' }}>
                    <span className={`text-xs font-medium whitespace-nowrap ${etapaVisual === 2 ? 'text-blue-600' : etapaVisual > 2 ? 'text-green-500' : 'text-gray-400'}`}>
                        {etapas[1].nome}
                    </span>
                </div>
                <div className="text-center" style={{ width: '80px' }}>
                    <span className={`text-xs font-medium whitespace-nowrap ${etapaVisual === 3 ? 'text-blue-600' : etapaVisual > 3 ? 'text-green-500' : 'text-gray-400'}`}>
                        {etapas[2].nome}
                    </span>
                </div>
            </div>
        </div>
    );
}