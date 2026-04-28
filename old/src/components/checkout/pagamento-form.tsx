"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import api from "@/services/api";
import { AxiosError } from "axios";
import { useCarrinho } from "@/components/carrinho/carrinho-context";

interface PagamentoFormProps {
    onVoltar: () => void;
    onProximo: () => void;
    alunoId?: number;
}

// Função para formatar valores monetários corretamente
const formatarMoeda = (valor: number): string => {
    return valor.toLocaleString('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
};

export default function PagamentoForm({ onVoltar, onProximo, alunoId }: PagamentoFormProps) {
    const { itens, totalPreco, totalParcelas, limparCarrinho } = useCarrinho();
    const [loading, setLoading] = useState(false);
    const [erro, setErro] = useState<string | null>(null);
    
    // Estado para o formulário de pagamento
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

    // Calcular valor da parcela (total / parcelas)
    const valorParcela = totalParcelas > 0 ? totalPreco / totalParcelas : 0;

    // DEBUG: Mostrar valores no console
    console.log('💰 Valores do pagamento:', {
        totalPreco,
        totalParcelas,
        valorParcela,
        totalFormatado: formatarMoeda(totalPreco),
        parcelaFormatada: formatarMoeda(valorParcela)
    });

    const handleChangeCartao = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value, type, checked } = e.target;
        setDadosCartao(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? checked : value
        }));
        setErro(null);
    };

    const formatarNumeroCartao = (value: string) => {
        return value
            .replace(/\D/g, '')
            .replace(/(\d{4})(?=\d)/g, '$1 ')
            .slice(0, 19);
    };

    const formatarValidade = (value: string) => {
        return value
            .replace(/\D/g, '')
            .replace(/(\d{2})(?=\d)/g, '$1/')
            .slice(0, 5);
    };

    const validarCartao = () => {
        if (formaPagamento !== 'cartao') return true;
        
        const erros = [];
        
        const numeroLimpo = dadosCartao.numero.replace(/\D/g, '');
        if (numeroLimpo.length !== 16) {
            erros.push('Número do cartão deve ter 16 dígitos');
        }
        
        const validadeLimpa = dadosCartao.validade.replace(/\D/g, '');
        if (validadeLimpa.length !== 4) {
            erros.push('Data de validade inválida (use MM/AA)');
        } else {
            const mes = parseInt(validadeLimpa.substring(0, 2));
            const ano = parseInt(validadeLimpa.substring(2, 4));
            const agora = new Date();
            const anoAtual = agora.getFullYear() % 100;
            const mesAtual = agora.getMonth() + 1;
            
            if (mes < 1 || mes > 12) {
                erros.push('Mês inválido');
            }
            if (ano < anoAtual || (ano === anoAtual && mes < mesAtual)) {
                erros.push('Cartão expirado');
            }
        }
        
        if (dadosCartao.cvc.length < 3 || dadosCartao.cvc.length > 4) {
            erros.push('CVC deve ter 3 ou 4 dígitos');
        }
        
        if (dadosCartao.nome.trim().length < 3) {
            erros.push('Nome no cartão inválido');
        }
        
        if (dadosCartao.endereco.trim().length < 5) {
            erros.push('Endereço de faturamento inválido');
        }
        
        if (erros.length > 0) {
            setErro(erros.join('. '));
            return false;
        }
        
        return true;
    };

    const criarPedido = async () => {
        try {
            const pedidoPayload = {
                aluno_id: alunoId,
                total: totalPreco,
                parcelas: totalParcelas,
                itens: itens.map(item => ({
                    id: item.id,
                    titulo: item.titulo,
                    quantidade: item.quantidade,
                    preco: item.preco
                }))
            };

            console.log('📦 Criando pedido:', pedidoPayload);
            
            const pedidoResponse = await api.post('/pedidos', pedidoPayload);
            console.log('📦 Pedido criado:', pedidoResponse.data);
            
            return pedidoResponse.data.pedido.id;
            
        } catch (error) {
            console.error('❌ Erro ao criar pedido:', error);
            throw new Error('Erro ao criar pedido');
        }
    };

    const handleSubmit = async () => {
        if (!validarCartao()) return;

        setLoading(true);
        setErro(null);

        try {
            if (!alunoId) {
                setErro('ID do aluno não encontrado. Volte e tente novamente.');
                setLoading(false);
                return;
            }

            if (itens.length === 0) {
                setErro('Carrinho vazio. Adicione itens antes de finalizar a compra.');
                setLoading(false);
                return;
            }

            // Criar pedido
            const pedidoId = await criarPedido();

            // Preparar payload do pagamento
            const payload = {
                aluno_id: alunoId,
                pedido_id: pedidoId,
                formaPagamento,
                responsavelFinanceiro: responsavel,
                parcelas: totalParcelas,
                ...(formaPagamento === 'cartao' && {
                    cartao: {
                        numero: dadosCartao.numero.replace(/\D/g, ''),
                        validade: dadosCartao.validade,
                        nome: dadosCartao.nome,
                        recorrente: dadosCartao.recorrente
                    }
                }),
                valor: totalPreco
            };

            console.log('📤 Enviando pagamento:', payload);
            
            const response = await api.post('/pagamentos', payload);
            console.log('📥 Resposta:', response.data);
            
            limparCarrinho();
            onProximo();

        } catch (error: unknown) {
            console.error('❌ Erro no pagamento:', error);
            
            if (error instanceof AxiosError) {
                if (error.response?.status === 400) {
                    setErro(error.response.data?.erro || 'Dados inválidos');
                } else if (error.response?.status === 404) {
                    setErro('Aluno não encontrado');
                } else if (error.response) {
                    setErro(error.response.data?.erro || 'Erro no processamento do pagamento');
                } else if (error.request) {
                    setErro('Não foi possível conectar ao servidor. Verifique se o backend está rodando.');
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
                    2. Pagamento
                </CardTitle>
            </CardHeader>

            <CardContent className="pt-6 space-y-6">
                {erro && (
                    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
                        {erro}
                    </div>
                )}

                {/* Responsável legal financeiro */}
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

                {/* Opções de pagamento */}
                <div className="space-y-3">
                    <h3 className="font-medium text-gray-700">Forma de pagamento</h3>
                    
                    <RadioGroup value={formaPagamento} onValueChange={setFormaPagamento} disabled={loading}>
                        {/* Boleto */}
                        <div className={`flex items-center justify-between p-3 border rounded-lg ${formaPagamento === 'boleto' ? 'border-blue-500 bg-blue-50' : ''}`}>
                            <div className="flex items-center space-x-2">
                                <RadioGroupItem value="boleto" id="boleto" />
                                <Label htmlFor="boleto" className="font-medium cursor-pointer">Boleto à vista</Label>
                            </div>
                            <span className="font-bold text-gray-900">
                                R$ {formatarMoeda(totalPreco)}
                            </span>
                        </div>

                        {/* PIX */}
                        <div className={`flex items-center justify-between p-3 border rounded-lg ${formaPagamento === 'pix' ? 'border-blue-500 bg-blue-50' : ''}`}>
                            <div className="flex items-center space-x-2">
                                <RadioGroupItem value="pix" id="pix" />
                                <Label htmlFor="pix" className="font-medium cursor-pointer">PIX</Label>
                            </div>
                            <span className="font-bold text-gray-900">
                                R$ {formatarMoeda(totalPreco)}
                            </span>
                        </div>

                        {/* Cartão parcelado */}
                        <div className={`p-3 border rounded-lg ${formaPagamento === 'cartao' ? 'border-blue-500 bg-blue-50' : ''}`}>
                            <div className="flex items-center space-x-2 mb-2">
                                <RadioGroupItem value="cartao" id="cartao" />
                                <Label htmlFor="cartao" className="font-medium cursor-pointer">Cartão parcelado</Label>
                            </div>
                            <div className="ml-6 text-sm text-gray-600">
                                <p>{totalParcelas}x R$ {formatarMoeda(valorParcela)}</p>
                                <p className="text-green-600 font-medium">
                                    {totalParcelas}x R$ {formatarMoeda(valorParcela)} sem juros
                                </p>
                            </div>
                        </div>
                    </RadioGroup>
                </div>

                {/* Dados do cartão */}
                {formaPagamento === "cartao" && (
                    <div className="space-y-4 border-t pt-4">
                        <h3 className="font-medium text-gray-700">Dados do cartão</h3>
                        
                        <div className="space-y-2">
                            <Label htmlFor="numero">Número do cartão</Label>
                            <Input
                                id="numero"
                                name="numero"
                                value={dadosCartao.numero}
                                onChange={handleChangeCartao}
                                placeholder="0000 0000 0000 0000"
                                className="w-full"
                                disabled={loading}
                                maxLength={19}
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="validade">Validade (MM/AA)</Label>
                                <Input
                                    id="validade"
                                    name="validade"
                                    value={dadosCartao.validade}
                                    onChange={handleChangeCartao}
                                    placeholder="MM/AA"
                                    disabled={loading}
                                    maxLength={5}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="cvc">CVC</Label>
                                <Input
                                    id="cvc"
                                    name="cvc"
                                    value={dadosCartao.cvc}
                                    onChange={handleChangeCartao}
                                    placeholder="123"
                                    disabled={loading}
                                    maxLength={4}
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="nome">Nome impresso no cartão</Label>
                            <Input
                                id="nome"
                                name="nome"
                                value={dadosCartao.nome}
                                onChange={handleChangeCartao}
                                placeholder="Como está no cartão"
                                disabled={loading}
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="endereco">Endereço para faturamento</Label>
                            <Input
                                id="endereco"
                                name="endereco"
                                value={dadosCartao.endereco}
                                onChange={handleChangeCartao}
                                placeholder="Rua, número, complemento"
                                disabled={loading}
                            />
                        </div>

                        <div className="flex items-center space-x-2">
                            <Checkbox 
                                id="recorrente" 
                                name="recorrente"
                                checked={dadosCartao.recorrente}
                                onCheckedChange={(checked) => 
                                    setDadosCartao(prev => ({ ...prev, recorrente: checked as boolean }))
                                }
                                disabled={loading}
                            />
                            <Label htmlFor="recorrente" className="text-sm">
                                Salvar cartão para compras futuras
                            </Label>
                        </div>
                    </div>
                )}

                {/* Total */}
                <div className="border-t pt-4">
                    <div className="flex justify-between items-center">
                        <span className="font-medium text-gray-700">Total:</span>
                        <span className="text-2xl font-bold text-gray-900">
                            R$ {formatarMoeda(totalPreco)}
                        </span>
                    </div>
                    {totalParcelas > 1 && (
                        <p className="text-sm text-gray-500 mt-1">
                            em até {totalParcelas}x de R$ {formatarMoeda(valorParcela)} sem juros
                        </p>
                    )}
                </div>

                <p className="text-sm text-gray-500 italic">
                    Após escolher a opção de pagamento, clique em Gerar Pedido.
                </p>

                {/* Botões */}
                <div className="flex gap-4 pt-4">
                    <Button
                        type="button"
                        variant="outline"
                        onClick={onVoltar}
                        disabled={loading}
                        className="flex-1 py-6 text-gray-700 border-gray-300 hover:bg-gray-50 rounded-lg"
                    >
                        Voltar
                    </Button>
                    <Button
                        type="button"
                        onClick={handleSubmit}
                        disabled={loading || itens.length === 0}
                        className="flex-1 py-6 bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:bg-gray-400"
                    >
                        {loading ? 'Processando...' : 'Gerar Pedido'}
                    </Button>
                </div>

                {/* Ajuda */}
                <div className="text-center pt-4">
                    <p className="text-sm text-gray-500 mb-2">Precisa de ajuda?</p>
                    <Link
                        href="https://wa.me/551239281616"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 text-green-600 hover:text-green-700 font-medium"
                    >
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12.004 2.003c-5.521 0-10 4.479-10 10 0 1.773.471 3.485 1.357 4.999L2 21.997l5.078-1.318c1.49.827 3.179 1.264 4.926 1.264 5.52 0 10-4.479 10-10 0-5.52-4.48-10-10-10zm5.657 14.486c-.239.672-1.19 1.23-1.957 1.358-.521.085-1.188.149-3.45-.74-2.893-1.136-4.757-3.92-4.902-4.099-.14-.18-1.171-1.556-1.171-2.97 0-1.414.743-2.11 1.005-2.398.262-.289.572-.361.762-.361.19 0 .38.001.547.01.193.008.424-.068.663.508.239.576.811 1.992.883 2.136.071.144.119.313.036.505-.084.192-.125.313-.25.482-.125.168-.262.375-.375.504-.125.125-.255.26-.109.51.145.25.646 1.067 1.386 1.726.954.85 1.756 1.113 2.005 1.238.25.125.396.108.542-.065.146-.173.625-.729.792-.979.168-.25.336-.209.567-.125.231.084 1.464.69 1.715.816.25.125.417.187.479.29.063.104.063.603-.176 1.255z" />
                        </svg>
                        Fale com um consultor
                    </Link>
                </div>
            </CardContent>
        </Card>
    );
}