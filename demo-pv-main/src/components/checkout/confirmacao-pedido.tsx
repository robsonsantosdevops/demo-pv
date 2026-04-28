"use client";

import { useState } from "react";
import api from "@/services/api";
import { useCheckoutTracking } from "@/lib/useCheckoutTracking";

interface AlunoData {
    nomeCompleto: string;
    cpf: string;
    email: string;
    telefone: string;
}

interface CursoData {
    id: string;
    titulo: string;
    preco: number;
    parcelas: number;
    valorParcela: number;
    descricao: string;
}

interface ConfirmacaoPedidoProps {
    alunoId: number;
    alunoData: AlunoData;
    curso: CursoData;
    onVoltar: () => void;
    onConfirmado: (pedidoId: number) => void;
}

export function ConfirmacaoPedido({
    alunoId,
    alunoData,
    curso,
    onVoltar,
    onConfirmado,
}: ConfirmacaoPedidoProps) {
    const { trackStep, trackError } = useCheckoutTracking();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const formatarCPF = (cpf: string) =>
        cpf.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");

    const formatarTelefone = (telefone: string) =>
        telefone.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3");

    const formatarMoeda = (valor: number) =>
        new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(valor);

    const handleConfirmar = async () => {
        setLoading(true);
        setError(null);

        // Rastreia início da confirmação do pedido
        trackStep('confirmacao', {
            acao: 'iniciado',
            aluno_id: alunoId,
            curso_id: curso.id,
            valor: curso.preco,
        });

        try {
            const response = await api.post("/pedidos", {
                aluno_id: alunoId,
                total: curso.preco,
                parcelas: curso.parcelas,
                itens: [
                    {
                        id: curso.id,
                        titulo: curso.titulo,
                        quantidade: 1,
                        preco: curso.preco,
                    },
                ],
            });

            const pedidoId = response.data.pedido.id;
            const correlationId = response.data.pedido.correlation_id;

            // Rastreia pedido criado com sucesso — inclui correlation_id para rastreio no Kibana
            trackStep('confirmacao', {
                acao: 'pedido_criado',
                pedido_id: pedidoId,
                correlation_id: correlationId,
                curso_id: curso.id,
                valor: curso.preco,
            });

            onConfirmado(pedidoId);

        } catch (err: unknown) {
            const axiosErr = err as { response?: { data?: { erro?: string } } };
            const mensagem = axiosErr.response?.data?.erro || "Erro ao criar pedido. Tente novamente.";

            trackError('confirmacao', new Error(mensagem));
            setError(mensagem);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">



            {/* Dados do Aluno */}
            <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <h3 className="font-semibold text-gray-800 mb-3 text-lg">Dados do Aluno</h3>
                <div className="space-y-3">
                    <div className="flex justify-between items-center py-1 border-b border-gray-50">
                        <span className="text-gray-500 text-sm">Nome completo</span>
                        <span className="font-medium text-gray-800 text-sm">{alunoData.nomeCompleto}</span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-gray-50">
                        <span className="text-gray-500 text-sm">CPF</span>
                        <span className="font-medium text-gray-800 text-sm">{formatarCPF(alunoData.cpf)}</span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-gray-50">
                        <span className="text-gray-500 text-sm">E-mail</span>
                        <span className="font-medium text-gray-800 text-sm break-all">{alunoData.email}</span>
                    </div>
                    <div className="flex justify-between items-center py-1">
                        <span className="text-gray-500 text-sm">Telefone</span>
                        <span className="font-medium text-gray-800 text-sm">{formatarTelefone(alunoData.telefone)}</span>
                    </div>
                </div>
            </div>

            {/* Resumo financeiro */}
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <h3 className="font-semibold text-gray-800 mb-3">Resumo do Pedido</h3>
                <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Subtotal</span>
                        <span className="font-medium">{formatarMoeda(curso.preco)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Parcelamento</span>
                        <span className="font-medium">
                            {curso.parcelas}x de {formatarMoeda(curso.preco / curso.parcelas)} sem juros
                        </span>
                    </div>
                    <div className="border-t pt-2 mt-2 flex justify-between font-bold text-base">
                        <span>Total</span>
                        <span>{formatarMoeda(curso.preco)}</span>
                    </div>
                </div>
            </div>

            {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                    {error}
                </div>
            )}

            {/* Botões */}
            <div className="flex gap-4 pt-2">
                <button
                    type="button"
                    onClick={onVoltar}
                    disabled={loading}
                    className="flex-1 px-6 py-3 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
                >
                    Voltar
                </button>
                <button
                    type="button"
                    onClick={handleConfirmar}
                    disabled={loading}
                    className="flex-1 px-6 py-3 bg-green-600 hover:bg-green-700 text-white font-semibold rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {loading ? "Criando pedido..." : "Confirmar Pedido"}
                </button>
            </div>
        </div>
    );
}
