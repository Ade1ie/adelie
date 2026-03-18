import React from 'react';
import Layout from '@/components/Layout';

interface Skill {
  name: string;
  level: string;
  category: string;
}

interface Experience {
  title: string;
  company: string;
  period: string;
  description: string;
}

const About: React.FC = () => {
  const skills: Skill[] = [
    { name: 'React', level: 'Advanced', category: 'Frontend' },
    { name: 'TypeScript', level: 'Advanced', category: 'Frontend' },
    { name: 'Tailwind CSS', level: 'Advanced', category: 'Frontend' },
    { name: 'Node.js', level: 'Intermediate', category: 'Backend' },
    { name: 'PostgreSQL', level: 'Intermediate', category: 'Database' },
    { name: 'Git', level: 'Advanced', category: 'Tools' },
  ];

  const experiences: Experience[] = [
    {
      title: 'Frontend Developer',
      company: 'Tech Solutions Inc.',
      period: '2022 - Present',
      description: 'Developing responsive web applications using React and TypeScript. Collaborating with design and backend teams to deliver high-quality user experiences.'
    },
    {
      title: 'Web Developer',
      company: 'Digital Agency Co.',
      period: '2020 - 2022',
      description: 'Built and maintained client websites with focus on performance and accessibility. Implemented modern frontend technologies and best practices.'
    },
    {
      title: 'Junior Developer',
      company: 'Startup Ventures',
      period: '2019 - 2020',
      description: 'Started career in web development, learning full-stack technologies and contributing to various projects.'
    }
  ];

  const skillCategories = [...new Set(skills.map(skill => skill.category))];

  return (
    <Layout>
      <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          {/* Hero Section */}
          <div className="text-center mb-16">
            <h1 className="text-4xl font-bold text-gray-900 mb-4">About Me</h1>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              Passionate developer with expertise in modern web technologies and a commitment to creating exceptional user experiences.
            </p>
          </div>

          {/* Bio Section */}
          <div className="bg-white rounded-lg shadow-md p-8 mb-12">
            <h2 className="text-2xl font-semibold text-gray-800 mb-6">Personal Bio</h2>
            <div className="prose prose-lg text-gray-600">
              <p className="mb-4">
                I'm a dedicated software developer with over 4 years of experience building web applications. 
                My journey in technology started with a curiosity about how things work, which evolved into 
                a passion for creating digital solutions that make a difference.
              </p>
              <p className="mb-4">
                When I'm not coding, you can find me exploring new technologies, contributing to open-source projects, 
                or sharing knowledge with the developer community. I believe in continuous learning and staying 
                up-to-date with industry trends.
              </p>
              <p>
                My approach to development combines technical expertise with user-centered design principles, 
                ensuring that every project delivers both functionality and exceptional user experience.
              </p>
            </div>
          </div>

          {/* Skills Section */}
          <div className="bg-white rounded-lg shadow-md p-8 mb-12">
            <h2 className="text-2xl font-semibold text-gray-800 mb-6">Skills & Expertise</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {skillCategories.map(category => (
                <div key={category} className="bg-gray-50 rounded-lg p-4">
                  <h3 className="font-semibold text-gray-700 mb-3">{category}</h3>
                  <div className="space-y-2">
                    {skills
                      .filter(skill => skill.category === category)
                      .map(skill => (
                        <div key={skill.name} className="flex justify-between items-center">
                          <span className="text-gray-600">{skill.name}</span>
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            skill.level === 'Advanced' ? 'bg-green-100 text-green-800' :
                            skill.level === 'Intermediate' ? 'bg-blue-100 text-blue-800' :
                            'bg-gray-100 text-gray-800'
                          }`}>
                            {skill.level}
                          </span>
                        </div>
                      ))
                    }
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Professional Background */}
          <div className="bg-white rounded-lg shadow-md p-8">
            <h2 className="text-2xl font-semibold text-gray-800 mb-6">Professional Background</h2>
            <div className="space-y-8">
              {experiences.map((exp, index) => (
                <div key={index} className="border-l-4 border-blue-500 pl-6 relative">
                  <div className="absolute -left-2 top-0 w-4 h-4 bg-blue-500 rounded-full"></div>
                  <div className="mb-2">
                    <h3 className="text-lg font-semibold text-gray-800">{exp.title}</h3>
                    <div className="flex flex-col sm:flex-row sm:items-center text-gray-600">
                      <span className="font-medium">{exp.company}</span>
                      <span className="hidden sm:block mx-2">•</span>
                      <span>{exp.period}</span>
                    </div>
                  </div>
                  <p className="text-gray-600">{exp.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default About;