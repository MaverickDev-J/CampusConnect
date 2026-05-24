export type Subject = {
    code: string;
    name: string;
};

// Based on schemas.py BranchEnum
export const BRANCHES = [
    { value: "COMP", label: "COMP (Computer Engineering)" },
    { value: "AI&DS", label: "AI&DS (Artificial Intelligence & Data Science)" },
    { value: "IT", label: "IT (Information Technology)" },
    { value: "EXTC", label: "EXTC (Electronics & Telecommunication)" },
    { value: "MECH", label: "MECH (Mechanical Engineering)" },
    { value: "CIVIL", label: "CIVIL (Civil Engineering)" },
];

// Based on schemas.py YearEnum
export const YEARS = [
    { value: 1, label: "First Year (FE)" },
    { value: 2, label: "Second Year (SE)" },
    { value: 3, label: "Third Year (TE)" },
    { value: 4, label: "Fourth Year (BE)" },
];

// Document Types from backend comment/logic
export const DOC_TYPES = [
    { value: "lecture", label: "Lecture" },
    { value: "notes", label: "Notes" },
    { value: "pyq", label: "PYQ (Question Paper)" },
    { value: "lab", label: "Lab Manual" },
    { value: "reference", label: "Reference Book" },
];

export const ACADEMIC_SUBJECTS: Record<string, Record<number, Subject[]>> = {
    "COMP": {
        1: [
            { code: "ma101", name: "Engineering Mathematics I" },
            { code: "ph101", name: "Engineering Physics" },
            { code: "cs101", name: "Programming in C" },
            { code: "ee101", name: "Basic Electrical Engineering" }
        ],
        2: [
            { code: "cs201", name: "Data Structures" },
            { code: "cs202", name: "Discrete Mathematics" },
            { code: "cs203", name: "Computer Organization" },
            { code: "cs204", name: "OOP (Java)" }
        ],
        3: [
            { code: "cs301", name: "Database Management Systems" },
            { code: "cs302", name: "Operating Systems" },
            { code: "cs303", name: "Computer Networks" },
            { code: "cs304", name: "Theory of Computation" }
        ],
        4: [
            { code: "cs401", name: "Machine Learning" },
            { code: "cs402", name: "Artificial Intelligence" },
            { code: "cs403", name: "Distributed Systems" },
            { code: "cs404", name: "Big Data Analytics" }
        ]
    },
    "AI&DS": {
        1: [
            { code: "ma101", name: "Engineering Mathematics I" },
            { code: "ph101", name: "Engineering Physics" },
            { code: "cs101", name: "Programming in C" },
            { code: "ee101", name: "Basic Electrical Engineering" }
        ],
        2: [
            { code: "ad201", name: "Data Structures" },
            { code: "ad202", name: "Probability & Statistics" },
            { code: "ad203", name: "Python Programming" },
            { code: "ad204", name: "Linear Algebra" }
        ],
        3: [
            { code: "ad301", name: "Machine Learning" },
            { code: "ad302", name: "Deep Learning" },
            { code: "ad303", name: "Data Mining" },
            { code: "ad304", name: "Big Data" }
        ],
        4: [
            { code: "ad401", name: "NLP" },
            { code: "ad402", name: "Computer Vision" },
            { code: "ad403", name: "Reinforcement Learning" },
            { code: "ad404", name: "AI Ethics" }
        ]
    },
    "IT": {
        1: [
            { code: "ma101", name: "Engineering Mathematics I" },
            { code: "ph101", name: "Engineering Physics" },
            { code: "cs101", name: "Programming in C" },
            { code: "ee101", name: "Basic Electrical Engineering" }
        ],
        2: [
            { code: "it201", name: "Data Structures" },
            { code: "it202", name: "OOP" },
            { code: "it203", name: "Web Technology" },
            { code: "it204", name: "Computer Organization" }
        ],
        3: [
            { code: "it301", name: "DBMS" },
            { code: "it302", name: "Operating Systems" },
            { code: "it303", name: "Computer Networks" },
            { code: "it304", name: "Software Engineering" }
        ],
        4: [
            { code: "it401", name: "Cloud Computing" },
            { code: "it402", name: "Cyber Security" },
            { code: "it403", name: "AI" },
            { code: "it404", name: "Big Data" }
        ]
    },
    "EXTC": {
        1: [ // Common subjects implied
            { code: "ma101", name: "Engineering Mathematics I" },
            { code: "ph101", name: "Engineering Physics" },
            { code: "cs101", name: "Programming in C" },
            { code: "ee101", name: "Basic Electrical Engineering" }
        ],
        2: [
            { code: "ec201", name: "Analog Electronics" },
            { code: "ec202", name: "Network Theory" },
            { code: "ec203", name: "Signals & Systems" },
            { code: "ec204", name: "Digital Electronics" }
        ],
        3: [
            { code: "ec301", name: "Microprocessors" },
            { code: "ec302", name: "Communication Systems" },
            { code: "ec303", name: "Control Systems" },
            { code: "ec304", name: "VLSI" }
        ],
        4: [
            { code: "ec401", name: "Wireless Communication" },
            { code: "ec402", name: "Embedded Systems" },
            { code: "ec403", name: "IoT" },
            { code: "ec404", name: "Radar Engineering" }
        ]
    },
    "MECH": {
        1: [
            { code: "ma101", name: "Engineering Mathematics I" },
            { code: "ph101", name: "Engineering Physics" },
            { code: "cs101", name: "Programming in C" },
            { code: "ee101", name: "Basic Electrical Engineering" }
        ],
        2: [
            { code: "me201", name: "Thermodynamics" },
            { code: "me202", name: "Fluid Mechanics" },
            { code: "me203", name: "Engineering Mechanics" },
            { code: "me204", name: "Material Science" }
        ],
        3: [
            { code: "me301", name: "Heat Transfer" },
            { code: "me302", name: "Machine Design" },
            { code: "me303", name: "Manufacturing Processes" },
            { code: "me304", name: "Dynamics of Machines" }
        ],
        4: [
            { code: "me401", name: "Robotics" },
            { code: "me402", name: "Automobile Engineering" },
            { code: "me403", name: "Industrial Engineering" },
            { code: "me404", name: "CAD/CAM" }
        ]
    },
    "CIVIL": {
        1: [
            { code: "ma101", name: "Engineering Mathematics I" },
            { code: "ph101", name: "Engineering Physics" },
            { code: "cs101", name: "Programming in C" },
            { code: "ee101", name: "Basic Electrical Engineering" }
        ],
        2: [
            { code: "cv201", name: "Engineering Mechanics" },
            { code: "cv202", name: "Structural Analysis" },
            { code: "cv203", name: "Fluid Mechanics" },
            { code: "cv204", name: "Building Materials" }
        ],
        3: [
            { code: "cv301", name: "Geotechnical Engineering" },
            { code: "cv302", name: "Environmental Engineering" },
            { code: "cv303", name: "Transportation Engineering" },
            { code: "cv304", name: "Hydrology" }
        ],
        4: [
            { code: "cv401", name: "Advanced Structural Design" },
            { code: "cv402", name: "Construction Management" },
            { code: "cv403", name: "Water Resource Engineering" },
            { code: "cv404", name: "Earthquake Engineering" }
        ]
    }
};
