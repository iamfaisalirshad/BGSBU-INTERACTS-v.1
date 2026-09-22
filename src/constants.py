ALL_DEPARTMENTS = {
    'School of Engineering & Technology': [
        'Computer Science & Engineering',
        'Information Technology',
        'Electronics & Communication Engineering',
        'Electrical Engineering',
        'Civil Engineering'
    ],
    'School of Management Studies': [
        'Business Administration',
        'Commerce',
        'Economics'
    ],
    'School of Biosciences & Biotechnology': [
        'Biotechnology',
        'Botany',
        'Zoology',
        'Microbiology'
    ],
    'School of Islamic Studies & Languages': [
        'Arabic',
        'Islamic Studies',
        'Urdu',
        'English',
        'Hindi'
    ],
    'School of Education': [
        'Education'
    ],
    'School of Mathematical & Computer Sciences': [
        'Mathematical Sciences',
        'Computer Sciences'
    ],
    'School of Nursing': [
        'Nursing'
    ],
    'School of Material Sciences & Nanotechnology': [
        'Physics',
        'Chemistry'
    ],
    'Other': [
        'Law',
        'Pharmacy',
        'Agriculture',
        'Veterinary Science',
        'Other',
        'Not Specified'
    ]
}

STUDENT_YEARS = {0: 'Degree Completed'} | {i: f'Semester {i}' for i in range(1, 11)}

DEGREE_SEMESTERS = {
    'Computer Science & Engineering': 8,
    'Information Technology': 8,
    'Electronics & Communication Engineering': 8,
    'Electrical Engineering': 8,
    'Civil Engineering': 8,
    'Business Administration': 6,
    'Commerce': 6,
    'Economics': 6,
    'Biotechnology': 6,
    'Botany': 6,
    'Zoology': 6,
    'Microbiology': 6,
    'Arabic': 6,
    'Islamic Studies': 6,
    'Urdu': 6,
    'English': 6,
    'Hindi': 6,
    'Education': 4,
    'Mathematical Sciences': 6,
    'Computer Sciences': 6,
    'Nursing': 8,
    'Physics': 6,
    'Chemistry': 6,
    'Law': 10,
    'Pharmacy': 8,
    'Agriculture': 8,
    'Veterinary Science': 10,
    'Other': 8,
    'Not Specified': 8,
}
