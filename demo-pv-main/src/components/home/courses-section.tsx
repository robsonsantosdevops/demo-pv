import { CursoCard } from "@/components/curso-card";

// Dados dos cursos com ID, preço e parcelas
const cursosData = [
    {
        id: "medicina-online", // ← ADICIONADO
        titulo: "Medicina Online",
        descricao: "Se o seu objetivo é ingressar em uma faculdade de Medicina, essa turma é para você. Com foco em física, química e biologia, oferece conteúdos aprofundados e simulados específicos para quem busca uma vaga nas melhores universidades da área.",
        inicio: "2 de fevereiro de 2026",
        colecao: "MED Digital",
        badges: ["Enem", "Fuvest", "Unicamp"],
        cor: "#2C77C4",
        preco: 14990, // ← ADICIONADO
        parcelas: 12 // ← ADICIONADO
    },
    {
        id: "ita-online", // ← ADICIONADO
        titulo: "Turma ITA Online",
        descricao: "Se o seu objetivo é ingressar em cursos de Engenharia nas instituições mais concorridas, essa turma é para você. Com aulas de nível avançado e professores experientes, o foco é preparar você para os desafios de vestibulares exigentes ITA e IME.",
        inicio: "12 de janeiro de 2026",
        colecao: "ITA Digital",
        badges: ["ITA", "IME", "Unicamp"],
        cor: "#4D6C45",
        preco: 16990, // ← ADICIONADO
        parcelas: 12 // ← ADICIONADO
    },
    {
        id: "enem-online", // ← ADICIONADO
        titulo: "Enem Online",
        descricao: "Se o seu objetivo é conquistar uma vaga em uma universidade pública ou garantir uma boa pontuação no ENEM, essa turma é para você. Com professores experientes e estratégias para melhorar seu desempenho em todas as áreas do exame.",
        inicio: "2 de março de 2026",
        colecao: "PIT Digital",
        badges: ["Enem", "Fuvest", "Unicamp"],
        cor: "#E65B0B",
        preco: 12990, // ← ADICIONADO
        parcelas: 10 // ← ADICIONADO
    },
    {
        id: "extensivo-manha", // ← ADICIONADO
        titulo: "Extensivo Manhã",
        descricao: "Prepare-se ao vivo no turno manha do extensivo com aulas online. Ela trabalha os conteúdos de forma aprofundada, ideal para quem tem mais tempo para se dedicar e quer uma preparação completa para o Enem e principais vestibulares.",
        inicio: "1 de fevereiro de 2026",
        colecao: "PIT Digital",
        badges: ["Etra", "Fuvest", "Unicamp"],
        cor: "#1C467E",
        preco: 13990, // ← ADICIONADO
        parcelas: 10 // ← ADICIONADO
    }
];

export function CoursesSection() {
    return (
        <section className="py-16 bg-[#E7E7E7]">
            <div className="container mx-auto px-4 max-w-7xl">
                <div className="bg-white rounded-3xl py-10 px-6 md:px-8 shadow-sm">
                    <h2 className="text-3xl text-center mb-12">
                        Encontre a <span className="font-bold">turma online</span> ideal para o tamanho dos seus sonhos
                    </h2>

                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
                        {cursosData.map((curso) => (
                            <CursoCard
                                key={curso.id} // ← USANDO ID COMO KEY
                                id={curso.id}
                                titulo={curso.titulo}
                                descricao={curso.descricao}
                                inicio={curso.inicio}
                                colecao={curso.colecao}
                                badges={curso.badges}
                                cor={curso.cor}
                                preco={curso.preco}
                                parcelas={curso.parcelas}
                            />
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
}