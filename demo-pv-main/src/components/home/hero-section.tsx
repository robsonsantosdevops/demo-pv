import Link from "next/link";

export function HeroSection() {
    return (
        <section className="relative bg-[#E7E7E7] -mt-30 pt-16.25 overflow-hidden">
            <div className="container mx-auto px-4 max-w-7xl">
                <div className="flex flex-col lg:flex-row items-center gap-8 lg:gap-12 min-h-125">
                    {/* Lado esquerdo - Texto e Cards */}
                    <div className="lg:w-1/2 space-y-1">
                        <h1 className="text-5xl font-bold text-gray-800 mb-1">Turmas Online</h1>
                        <p className="text-lg text-gray-700 leading-relaxed mb-20">
                            Prepare-se para os principais vestibulares do país com a estrutura pedagógica
                            e a qualidade reconhecida do curso que é referência e liderança em aprovações.
                            E o melhor: sem sair de casa.
                        </p>
                        {/* Cards de Promoções */}
                        <div className="grid grid-cols-2 gap-4">
                            {/* Concurso de Bolsas Card - Laranja */}
                            <Link href="/checkout" className="block">
                                <div 
                                    className="rounded-2xl p-5 flex flex-col items-center text-center transition-all duration-300 hover:scale-105 hover:shadow-xl cursor-pointer"
                                    style={{ 
                                        backgroundColor: '#E04816',
                                        border: 'none'
                                    }}
                                >
                                    <h3 className="text-lg font-bold mb-2" style={{ color: '#FDFAF8' }}>
                                        Concurso de Bolsas
                                    </h3>
                                    <p className="text-sm mb-3" style={{ color: '#FDFAF8' }}>
                                        Participe da prova e concorra a bolsas de até 100%.
                                    </p>
                                    <button 
                                        className="font-bold text-sm px-4 py-2 rounded-full transition-all duration-300 hover:scale-105 hover:shadow-md"
                                        style={{ 
                                            backgroundColor: '#FDFAF8',
                                            color: '#E04816'
                                        }}
                                    >
                                        SAIBA MAIS →
                                    </button>
                                </div>
                            </Link>
                            
                            {/* Bolsa Desempenho Card - Azul */}
                            <Link href="/checkout" className="block">
                                <div 
                                    className="rounded-2xl p-5 flex flex-col items-center text-center transition-all duration-300 hover:scale-105 hover:shadow-xl cursor-pointer"
                                    style={{ 
                                        backgroundColor: '#1E5E9B',
                                        border: 'none'
                                    }}
                                >
                                    <h3 className="text-lg font-bold mb-2" style={{ color: '#FDFAF8' }}>
                                        Bolsa Desempenho
                                    </h3>
                                    <p className="text-sm mb-3" style={{ color: '#FDFAF8' }}>
                                        Envie seu boletim com notas de outros vestibulares e obtenha descontos.
                                    </p>
                                    <button 
                                        className="font-bold text-sm px-4 py-2 rounded-full transition-all duration-300 hover:scale-105 hover:shadow-md"
                                        style={{ 
                                            backgroundColor: '#FDFAF8',
                                            color: '#1E5E9B'
                                        }}
                                    >
                                        SAIBA MAIS →
                                    </button>
                                </div>
                            </Link>
                        </div>
                    </div>
                    {/* Lado direito - Imagem */}
                    <div className="lg:w-1/2 flex justify-center items-start">
                        <img
                            src="/image.png"
                            alt="Alunos aprovados Poliedro"
                            width={1000}
                            height={716}
                            style={{
                                width: "100%",
                                height: "auto",
                                maxWidth: "1000px",
                                objectFit: "contain",
                                marginTop: "-80px",
                            }}
                        />
                    </div>
                </div>
            </div>
        </section>
    );
}