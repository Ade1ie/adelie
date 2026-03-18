import Head from 'next/head'

export default function Home() {
  return (
    <>
      <Head>
        <title>Personal Workspace</title>
        <meta name="description" content="Your personal digital workspace" />
      </Head>
      
      <main className="min-h-screen py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h1 className="text-4xl font-bold text-gray-900 mb-4">
              Welcome to Your Personal Workspace
            </h1>
            <p className="text-lg text-gray-600 mb-8">
              A private, customizable environment for your projects and productivity
            </p>
            
            <div className="grid md:grid-cols-2 gap-6 mt-12">
              <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h3 className="text-xl font-semibold mb-3">Organize</h3>
                <p className="text-gray-600">Keep your projects and notes organized in one place</p>
              </div>
              
              <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h3 className="text-xl font-semibold mb-3">Customize</h3>
                <p className="text-gray-600">Tailor your workspace to fit your workflow</p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  )
}