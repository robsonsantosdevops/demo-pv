"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { CheckoutLayout } from "@/components/checkout/checkout-layout";
import { CheckoutStepper } from "@/components/checkout/checkout-stepper";
import { CheckoutForm as FormularioCheckout } from "@/components/checkout/checkout-form";
import PagamentoForm from "@/components/checkout/pagamento-form";
import { useCarrinho } from "@/components/carrinho/carrinho-context";

export default function CheckoutPage() {
    const router = useRouter();
    const { itens, totalPreco, totalParcelas, limparCarrinho } = useCarrinho();
    const [etapaAtual, setEtapaAtual] = useState<number>(1);
    const [alunoId, setAlunoId] = useState<number | undefined>();

    // Redirecionar se carrinho estiver vazio
    useEffect(() => {
        if (itens.length === 0 && etapaAtual === 1) {
            router.push("/carrinho");
        }
    }, [itens, etapaAtual, router]);

    const handleAlunoCriado = (id?: number) => {
        if (id) {
            setAlunoId(id);
            irParaProximaEtapa();
        }
    };

    const irParaProximaEtapa = () => {
        if (etapaAtual < 3) {
            setEtapaAtual(etapaAtual + 1);
        }
    };

    const irParaEtapaAnterior = () => {
        if (etapaAtual > 1) {
            setEtapaAtual(etapaAtual - 1);
        }
    };

    const handlePagamentoConcluido = () => {
        // Limpar carrinho após pagamento bem-sucedido
        limparCarrinho();
        irParaProximaEtapa();
    };

    // Se carrinho estiver vazio e não for etapa de confirmação, mostra loading
    if (itens.length === 0 && etapaAtual !== 3) {
        return (
            <CheckoutLayout>
                <div className="max-w-2xl mx-auto w-full text-center py-12">
                    <p className="text-gray-600">Redirecionando para o carrinho...</p>
                </div>
            </CheckoutLayout>
        );
    }

    return (
        <CheckoutLayout>
            <div className="max-w-2xl mx-auto w-full">
                <div className="flex items-center justify-between mb-8">
                    <div className="flex flex-col">
                        <Link href="/" className="flex items-center">
                            <Image
                                src="/logo-poliedro-curso (2).svg"
                                alt="Poliedro Cursos"
                                width={160}
                                height={40}
                                className="h-10 w-auto"
                                priority
                            />
                        </Link>
                        <span className="text-xs text-gray-500 font-medium tracking-wide mt-0.5">
                            PRÉ-VESTIBULAR ONLINE
                        </span>
                    </div>
                    <CheckoutStepper etapaAtual={etapaAtual as 1 | 2 | 3} />
                </div>

                {/* Resumo do pedido (visível em todas as etapas) */}
                {itens.length > 0 && (
                    <div className="bg-blue-50 border border-blue-100 rounded-lg p-4 mb-6">
                        <h3 className="text-sm font-semibold text-blue-800 mb-2">Resumo do pedido</h3>
                        {itens.map((item) => (
                            <div key={item.id} className="flex justify-between text-sm text-gray-600 mb-1">
                                <span>{item.titulo} x{item.quantidade}</span>
                                <span>R$ {(item.preco * item.quantidade).toLocaleString('pt-BR')},00</span>
                            </div>
                        ))}
                        <div className="border-t border-blue-200 mt-2 pt-2 flex justify-between font-bold text-blue-800">
                            <span>Total:</span>
                            <span>R$ {totalPreco.toLocaleString('pt-BR')},00</span>
                        </div>
                        <div className="text-xs text-blue-600 mt-1">
                            em até {totalParcelas}x sem juros
                        </div>
                    </div>
                )}

                <div className="w-full">
                    {etapaAtual === 1 && (
                        <FormularioCheckout 
                            onProximo={handleAlunoCriado}
                            etapaAtual={1}
                        />
                    )}
                    
                    {etapaAtual === 2 && (
                        <PagamentoForm
                            onVoltar={irParaEtapaAnterior}
                            onProximo={handlePagamentoConcluido}
                            alunoId={alunoId}
                        />
                    )}
                    
                    {etapaAtual === 3 && (
                        <div className="text-center py-12">
                            <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                <svg className="w-10 h-10 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <h2 className="text-2xl font-bold text-gray-800 mb-2">Pagamento Confirmado!</h2>
                            <p className="text-gray-600 mb-2">Sua matrícula foi realizada com sucesso.</p>
                            <p className="text-sm text-gray-500 mb-6">
                                Um e-mail de confirmação foi enviado para você.
                            </p>
                            <Link href="/" className="inline-block px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                                Voltar para página inicial
                            </Link>
                        </div>
                    )}
                </div>
            </div>
        </CheckoutLayout>
    );
}