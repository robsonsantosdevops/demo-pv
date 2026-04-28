import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

interface PromotionCardsProps {
    variant?: 'default' | 'hero';
}

export function PromotionCards({ variant = 'default' }: PromotionCardsProps) {
    if (variant === 'hero') {
        return (
            <div className="grid grid-cols-2 gap-4 mt-4">
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
                            className="font-bold text-sm px-4 py-2 rounded-full transition-all hover:opacity-90"
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
                            className="font-bold text-sm px-4 py-2 rounded-full transition-all hover:opacity-90"
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
        );
    }
}