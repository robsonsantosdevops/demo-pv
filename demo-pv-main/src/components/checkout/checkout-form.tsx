"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import api from "@/services/api";
import { AxiosError } from "axios";
import { useCheckoutTracking } from "@/lib/useCheckoutTracking";

interface AlunoData {
    nomeCompleto: string;
    cpf: string;
    email: string;
    telefone: string;
}

interface CheckoutFormProps {
    // Agora passa o id E os dados do formulário — necessário para a tela de confirmação
    onProximo?: (alunoId: number, dados: AlunoData) => void;
    etapaAtual: 1 | 2 | 3 | 4;
}

export function CheckoutForm({ onProximo, etapaAtual }: CheckoutFormProps) {
    const router = useRouter();
    const { trackStep, trackError } = useCheckoutTracking();

    const [formData, setFormData] = useState<AlunoData>({
        nomeCompleto: "",
        cpf: "",
        email: "",
        telefone: "",
    });
    const [aceitaPolitica, setAceitaPolitica] = useState(false);
    const [loading, setLoading] = useState(false);
    const [erro, setErro] = useState<string | null>(null);

    const isFormValid = () =>
        formData.nomeCompleto.trim() !== "" &&
        formData.cpf.trim() !== "" &&
        formData.email.trim() !== "" &&
        formData.telefone.trim() !== "" &&
        aceitaPolitica === true;

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
        setErro(null);
    };

    const handleCancel = () => {
        trackStep('dados_pessoais', { acao: 'cancelado' });
        router.push('/');
    };

    const handleSubmit = async () => {
        if (!isFormValid()) return;

        setLoading(true);
        setErro(null);
        trackStep('dados_pessoais', { acao: 'iniciado' });

        try {
            const response = await api.post('/alunos', {
                nomeCompleto: formData.nomeCompleto,
                cpf: formData.cpf,
                email: formData.email,
                telefone: formData.telefone
            });

            trackStep('dados_pessoais', {
                acao: 'concluido',
                aluno_id: response.data.aluno.id,
            });

            if (onProximo) {
                // Passa o id E os dados do formulário para a próxima etapa
                onProximo(response.data.aluno.id, formData);
            }

        } catch (error) {
            if (error instanceof AxiosError) {
                trackError('dados_pessoais', new Error(
                    error.response?.data?.erro || error.message
                ));

                if (error.response?.status === 409) {
                    setErro(error.response.data?.erro || 'Dados já cadastrados');
                } else if (error.response?.status === 400) {
                    const detalhes = error.response.data?.detalhes;
                    setErro(detalhes?.[0] || 'Dados inválidos. Verifique as informações.');
                } else if (error.response) {
                    setErro('Erro no servidor. Tente novamente mais tarde.');
                } else if (error.request) {
                    setErro('Não foi possível conectar ao servidor.');
                } else {
                    setErro('Ocorreu um erro. Tente novamente.');
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
                    1. Dados do Aluno
                </CardTitle>
            </CardHeader>

            <CardContent className="pt-6 space-y-5">
                {erro && (
                    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
                        {erro}
                    </div>
                )}

                <div className="space-y-2">
                    <label htmlFor="nomeCompleto" className="text-sm font-medium text-gray-700 block">
                        Nome Completo
                    </label>
                    <Input
                        id="nomeCompleto"
                        name="nomeCompleto"
                        type="text"
                        value={formData.nomeCompleto}
                        onChange={handleChange}
                        placeholder="Nome Completo"
                        className="w-full p-3 border border-gray-300 rounded-lg"
                        required
                        disabled={loading}
                    />
                </div>

                <div className="space-y-2">
                    <label htmlFor="cpf" className="text-sm font-medium text-gray-700 block">
                        CPF
                    </label>
                    <Input
                        id="cpf"
                        name="cpf"
                        type="text"
                        value={formData.cpf}
                        onChange={handleChange}
                        placeholder="000.000.000-00"
                        className="w-full p-3 border border-gray-300 rounded-lg"
                        required
                        disabled={loading}
                    />
                </div>

                <div className="space-y-2">
                    <label htmlFor="email" className="text-sm font-medium text-gray-700 block">
                        E-mail
                    </label>
                    <Input
                        id="email"
                        name="email"
                        type="email"
                        value={formData.email}
                        onChange={handleChange}
                        placeholder="E-mail"
                        className="w-full p-3 border border-gray-300 rounded-lg"
                        required
                        disabled={loading}
                    />
                </div>

                <div className="space-y-2">
                    <label htmlFor="telefone" className="text-sm font-medium text-gray-700 block">
                        Telefone
                    </label>
                    <Input
                        id="telefone"
                        name="telefone"
                        type="tel"
                        value={formData.telefone}
                        onChange={handleChange}
                        placeholder="(00) 00000-0000"
                        className="w-full p-3 border border-gray-300 rounded-lg"
                        required
                        disabled={loading}
                    />
                </div>

                <div className="flex items-start space-x-3 pt-2">
                    <Checkbox
                        id="aceitaPolitica"
                        checked={aceitaPolitica}
                        onCheckedChange={(checked) => setAceitaPolitica(checked as boolean)}
                        className="mt-1"
                        disabled={loading}
                    />
                    <label htmlFor="aceitaPolitica" className="text-sm text-gray-600 leading-relaxed">
                        Li e concordo com a{" "}
                        <Link href="/politica-de-privacidade" className="text-blue-600 hover:underline font-medium">
                            Política de Privacidade
                        </Link>{" "}
                        e Proteção de Dados.
                    </label>
                </div>

                {!isFormValid() && !loading && (
                    <p className="text-xs text-gray-500 text-center pt-2">
                        Preencha todos os campos e aceite os termos para continuar
                    </p>
                )}

                <div className="flex gap-4 pt-6 border-t border-gray-100">
                    <Button
                        type="button"
                        variant="outline"
                        onClick={handleCancel}
                        disabled={loading}
                        className="flex-1 py-6 text-gray-700 border-gray-300 hover:bg-gray-50 rounded-lg"
                    >
                        Cancelar
                    </Button>

                    <Button
                        type="button"
                        onClick={handleSubmit}
                        disabled={!isFormValid() || loading}
                        className={`flex-1 py-6 text-white rounded-lg ${
                            !isFormValid() || loading
                                ? 'bg-gray-400 cursor-not-allowed'
                                : 'bg-blue-600 hover:bg-blue-700'
                        }`}
                    >
                        {loading ? 'Enviando...' : 'Próximo'}
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}
