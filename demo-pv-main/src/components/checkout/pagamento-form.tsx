// src/components/checkout/pagamento-form.tsx
"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import api from "@/services/api";
import { AxiosError } from "axios";
import { useCarrinho } from "@/components/carrinho/carrinho-context";
import { useCheckoutTracking } from "@/lib/useCheckoutTracking";

interface PagamentoFormProps {
    onVoltar: () => void;
    onProximo: () => void;
    alunoId?: number;
    pedidoId?: number;  // ← NOVO: receber o pedidoId da tela de confirmação
    valor?: number;
    parcelasDisponiveis?: number;
}

const formatarMoeda = (valor: number): string => {
    return valor.toLocaleString('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
};

export default function PagamentoForm({
    onVoltar,
    onProximo,
    alunoId,
    pedidoId,
    valor,
    parcelasDisponiveis,
}: PagamentoFormProps) {
    const { itens, totalPreco, totalParcelas } = useCarrinho();
    const { trackStep, trackError } = useCheckoutTracking();

    const precoTotal = valor ?? totalPreco;
    const parcelasTotal = parcelasDisponiveis ?? totalParcelas;

    const [loading, setLoading] = useState(false);
    const [erro, setErro] = useState<string | null>(null);
    const [formaPagamento, setFormaPagamento] = useState<string>("cartao");
    const [responsavel, setResponsavel] = useState(false);
    const [dadosCartao, setDadosCartao] = useState({
        numero: "",
        validade: "",
        cvc: "",
        nome: "",
        endereco: "",
        recorrente: false
    });

    const valorParcela = parcelasTotal > 0 ? precoTotal / parcelasTotal : 0;

    const handleChangeCartao = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value, type, checked } = e.target;
        setDadosCartao(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? checked : value
        }));
        setErro(null);
    };

    const validarCartao = () => {
        if (formaPagamento !== 'cartao') return true;

        const erros = [];
        const numeroLimpo = dadosCartao.numero.replace(/\D/g, '');
        if (numeroLimpo.length !== 16) erros.push('Número do cartão deve ter 16 dígitos');

        const validadeLimpa = dadosCartao.validade.replace(/\D/g, '');
        if (validadeLimpa.length !== 4) {
            erros.push('Data de validade inválida (use MM/AA)');
        } else {
            const mes = parseInt(validadeLimpa.substring(0, 2));
            const ano = parseInt(validadeLimpa.substring(2, 4));
            const agora = new Date();
            const anoAtual = agora.getFullYear() % 100;
            const mesAtual = agora.getMonth() + 1;
            if (mes < 1 || mes > 12) erros.push('Mês inválido');
            if (ano < anoAtual || (ano === anoAtual && mes < mesAtual)) erros.push('Cartão expirado');
        }

        if (dadosCartao.cvc.length < 3 || dadosCartao.cvc.length > 4) erros.push('CVC deve ter 3 ou 4 dígitos');
        if (dadosCartao.nome.trim().length < 3) erros.push('Nome no cartão inválido');
        if (dadosCartao.endereco.trim().length < 5) erros.push('Endereço de faturamento inválido');

        if (erros.length > 0) {
            setErro(erros.join('. '));
            return false;
        }
        return true;
    };

    const handleSubmit = async () => {
        if (!validarCartao()) return;

        setLoading(true);
        setErro(null);

        trackStep('pagamento', {
            forma_pagamento: formaPagamento,
            valor: precoTotal,
            parcelas: parcelasTotal,
            itens: itens.length,
        });

        try {
            if (!alunoId) {
                setErro('ID do aluno não encontrado. Volte e tente novamente.');
                setLoading(false);
                return;
            }

            if (!pedidoId) {
                setErro('ID do pedido não encontrado. Volte e tente novamente.');
                setLoading(false);
                return;
            }

            if (itens.length === 0) {
                setErro('Carrinho vazio. Adicione itens antes de finalizar a compra.');
                setLoading(false);
                return;
            }

            const payload = {
                aluno_id: alunoId,
                pedido_id: pedidoId,
                formaPagamento,
                responsavelFinanceiro: responsavel,
                parcelas: parcelasTotal,
                ...(formaPagamento === 'cartao' && {
                    cartao: {
                        numero: dadosCartao.numero.replace(/\D/g, ''),
                        validade: dadosCartao.validade,
                        nome: dadosCartao.nome,
                        recorrente: dadosCartao.recorrente
                    }
                }),
                valor: precoTotal
            };

            const response = await api.post('/pagamentos', payload);

            trackStep('confirmacao', {
                forma_pagamento: formaPagamento,
                valor: precoTotal,
                parcelas: parcelasTotal,
                pedido_id: pedidoId,
                protocolo: response.data.pagamento?.protocolo,
            });

            onProximo();

        } catch (error: unknown) {
            if (error instanceof AxiosError) {
                trackError('pagamento', new Error(
                    error.response?.data?.erro || error.message
                ));

                if (error.response?.status === 400) {
                    setErro(error.response.data?.erro || 'Dados inválidos');
                } else if (error.response?.status === 404) {
                    setErro('Aluno não encontrado');
                } else if (error.response) {
                    setErro(error.response.data?.erro || 'Erro no processamento do pagamento');
                } else if (error.request) {
                    setErro('Não foi possível conectar ao servidor.');
                } else {
                    setErro('Erro ao processar pagamento. Tente novamente.');
                }
            } else {
                setErro('Ocorreu um erro inesperado.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <Card className="border-2 border-gray-200 shadow-lg">
            <CardHeader className="border-b border-gray-100 pb-6">
                <CardTitle className="text-2xl font-bold text-center text-gray-800">
                    3. Pagamento
                </CardTitle>
            </CardHeader>

            <CardContent className="pt-6 space-y-6">
                {erro && (
                    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
                        {erro}
                    </div>
                )}

                <div className="space-y-3">
                    <h3 className="font-medium text-gray-700">Responsável financeiro</h3>
                    <div className="flex items-center space-x-2">
                        <Checkbox
                            id="responsavel"
                            checked={responsavel}
                            onCheckedChange={(checked) => setResponsavel(checked as boolean)}
                            disabled={loading}
                        />
                        <Label htmlFor="responsavel" className="text-sm text-gray-600">
                            Cadastrar responsável legal financeiro
                        </Label>
                    </div>
                </div>

                <div className="space-y-3">
                    <h3 className="font-medium text-gray-700">Forma de pagamento</h3>
                    <RadioGroup value={formaPagamento} onValueChange={setFormaPagamento} disabled={loading}>
                        <div className={`flex items-center justify-between p-3 border rounded-lg ${formaPagamento === 'boleto' ? 'border-blue-500 bg-blue-50' : ''}`}>
                            <div className="flex items-center space-x-2">
                                <RadioGroupItem value="boleto" id="boleto" />
                                <Label htmlFor="boleto" className="font-medium cursor-pointer">Boleto à vista</Label>
                            </div>
                            <span className="font-bold text-gray-900">R$ {formatarMoeda(precoTotal)}</span>
                        </div>

                        <div className={`flex items-center justify-between p-3 border rounded-lg ${formaPagamento === 'pix' ? 'border-blue-500 bg-blue-50' : ''}`}>
                            <div className="flex items-center space-x-2">
                                <RadioGroupItem value="pix" id="pix" />
                                <Label htmlFor="pix" className="font-medium cursor-pointer">PIX</Label>
                            </div>
                            <span className="font-bold text-gray-900">R$ {formatarMoeda(precoTotal)}</span>
                        </div>

                        <div className={`p-3 border rounded-lg ${formaPagamento === 'cartao' ? 'border-blue-500 bg-blue-50' : ''}`}>
                            <div className="flex items-center space-x-2 mb-2">
                                <RadioGroupItem value="cartao" id="cartao" />
                                <Label htmlFor="cartao" className="font-medium cursor-pointer">Cartão parcelado</Label>
                            </div>
                            <div className="ml-6 text-sm text-gray-600">
                                <p>{parcelasTotal}x R$ {formatarMoeda(valorParcela)}</p>
                                <p className="text-green-600 font-medium">{parcelasTotal}x R$ {formatarMoeda(valorParcela)} sem juros</p>
                            </div>
                        </div>
                    </RadioGroup>
                </div>

                {formaPagamento === "cartao" && (
                    <div className="space-y-4 border-t pt-4">
                        <h3 className="font-medium text-gray-700">Dados do cartão</h3>

                        <div className="space-y-2">
                            <Label htmlFor="numero">Número do cartão</Label>
                            <Input id="numero" name="numero" value={dadosCartao.numero} onChange={handleChangeCartao} placeholder="0000 0000 0000 0000" disabled={loading} maxLength={19} />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="validade">Validade (MM/AA)</Label>
                                <Input id="validade" name="validade" value={dadosCartao.validade} onChange={handleChangeCartao} placeholder="MM/AA" disabled={loading} maxLength={5} />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="cvc">CVC</Label>
                                <Input id="cvc" name="cvc" value={dadosCartao.cvc} onChange={handleChangeCartao} placeholder="123" disabled={loading} maxLength={4} />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="nome">Nome impresso no cartão</Label>
                            <Input id="nome" name="nome" value={dadosCartao.nome} onChange={handleChangeCartao} placeholder="Como está no cartão" disabled={loading} />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="endereco">Endereço para faturamento</Label>
                            <Input id="endereco" name="endereco" value={dadosCartao.endereco} onChange={handleChangeCartao} placeholder="Rua, número, complemento" disabled={loading} />
                        </div>

                        <div className="flex items-center space-x-2">
                            <Checkbox
                                id="recorrente"
                                checked={dadosCartao.recorrente}
                                onCheckedChange={(checked) =>
                                    setDadosCartao(prev => ({ ...prev, recorrente: checked as boolean }))
                                }
                                disabled={loading}
                            />
                            <Label htmlFor="recorrente" className="text-sm">Salvar cartão para compras futuras</Label>
                        </div>
                    </div>
                )}

                <div className="border-t pt-4">
                    <div className="flex justify-between items-center">
                        <span className="font-medium text-gray-700">Total:</span>
                        <span className="text-2xl font-bold text-gray-900">R$ {formatarMoeda(precoTotal)}</span>
                    </div>
                    {parcelasTotal > 1 && (
                        <p className="text-sm text-gray-500 mt-1">em até {parcelasTotal}x de R$ {formatarMoeda(valorParcela)} sem juros</p>
                    )}
                </div>

                <p className="text-sm text-gray-500 italic">
                    Após escolher a opção de pagamento, clique em Finalizar Compra.
                </p>

                <div className="flex gap-4 pt-4">
                    <Button type="button" variant="outline" onClick={onVoltar} disabled={loading} className="flex-1 py-6 text-gray-700 border-gray-300 hover:bg-gray-50 rounded-lg">
                        Voltar
                    </Button>
                    <Button type="button" onClick={handleSubmit} disabled={loading || itens.length === 0} className="flex-1 py-6 bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:bg-gray-400">
                        {loading ? 'Processando...' : 'Finalizar Compra'}
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}
