import Link from "next/link";
import { Button } from "@/components/ui/button";
import { CheckCircle } from "lucide-react";
import { CheckoutLayout } from "@/components/checkout/checkout-layout";

export default function SucessoPage() {
    return (
        <CheckoutLayout>
            <div className="text-center py-12">
                <div className="flex justify-center mb-6">
                    <CheckCircle className="h-20 w-20 text-green-500" />
                </div>
                <h1 className="text-3xl font-bold text-gray-800 mb-4">
                    Cadastro realizado com sucesso!
                </h1>
                <p className="text-lg text-gray-600 mb-8">
                    Seus dados foram enviados. Em breve entraremos em contato.
                </p>
                <Link href="/">
                    <Button className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-6 text-lg rounded-lg">
                        Voltar para a página inicial
                    </Button>
                </Link>
            </div>
        </CheckoutLayout>
    );
}