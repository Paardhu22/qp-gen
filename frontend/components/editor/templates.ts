export const defaultHeaderHTML = `
    <div data-type="paper-header-block">
      <h1>PA1 - CENTRAL OFFICE</h1>
      <h2>CBSE - Question Paper</h2>
      <table>
        <thead>
          <tr>
            <th>SUBJECT</th>
            <th>GRADE</th>
            <th>SET</th>
            <th>MAX MARK</th>
            <th>TIME</th>
            <th>DATE</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>English</td>
            <td>VI</td>
            <td>A</td>
            <td>40</td>
            <td>90 min</td>
            <td>________</td>
          </tr>
        </tbody>
      </table>
    </div>
`;

export const templates = {
  cbse: `
    <div data-type="paper-header-block">
      <h1>PA1 - CENTRAL OFFICE</h1>
      <h2>CBSE - Question Paper</h2>
      <table>
        <thead>
          <tr>
            <th>SUBJECT</th>
            <th>GRADE</th>
            <th>SET</th>
            <th>MAX MARK</th>
            <th>TIME</th>
            <th>DATE</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>English</td>
            <td>VI</td>
            <td>A</td>
            <td>40</td>
            <td>90 min</td>
            <td>________</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div data-type="instruction-block">
      <ol>
        <li>All questions are compulsory. Internal choices are provided in some questions.</li>
        <li>Write answers in the provided space only.</li>
        <li>Use of calculator is not permitted.</li>
      </ol>
    </div>

    <div data-type="section-block">SECTION A</div>

    <div data-type="question-block" data-marks="1" data-number="1">
      <p>Which of the following is NOT a web service?</p>
      <ol>
        <li>Sending an email via a webmail client</li>
        <li>Making online transactions through a banking portal</li>
        <li>Sharing files through Bluetooth</li>
        <li>Conducting online classes for students</li>
      </ol>
    </div>

    <div data-type="question-block" data-marks="1" data-number="2">
      <p>What does TCP/IP stand for?</p>
      <ol>
        <li>Transmission Control Program/Internet Protocol</li>
        <li>Transfer Control Program/Internet Protocol</li>
        <li>Transfer Control Protocol/Internet Provider</li>
        <li>Transmission Control Protocol/Internet Protocol</li>
      </ol>
    </div>

    <div data-type="section-block">SECTION B</div>

    <div data-type="question-block" data-marks="2" data-number="3">
      <p>Define information retrieval with one example.</p>
    </div>
  `,

  minimalSchool: `
    <div data-type="paper-header-block">
      <h1>GREENWOOD PUBLIC SCHOOL</h1>
      <h2>UNIT TEST - APRIL 2026</h2>
      <table>
        <thead>
          <tr>
            <th>SUBJECT</th>
            <th>GRADE</th>
            <th>SET</th>
            <th>MAX MARK</th>
            <th>TIME</th>
            <th>DATE</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Science</td>
            <td>IX</td>
            <td>A</td>
            <td>30</td>
            <td>60 min</td>
            <td>19/04/2026</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div data-type="instruction-block">
      <ol>
        <li>All questions are compulsory.</li>
        <li>Answer in clear, concise language.</li>
        <li>Draw diagrams wherever necessary.</li>
      </ol>
    </div>

    <div data-type="section-block">SECTION A</div>

    <div data-type="question-block" data-marks="1" data-number="1">
      <p>State one function of the human respiratory system.</p>
    </div>

    <div data-type="question-block" data-marks="1" data-number="2">
      <p>What is the SI unit of pressure?</p>
    </div>
  `,

  university: `
    <div data-type="paper-header-block">
      <h1>UNIVERSITY OF TECHNOLOGY</h1>
      <h2>DEPARTMENT OF COMPUTER SCIENCE</h2>
      <table>
        <thead>
          <tr>
            <th>COURSE</th>
            <th>CODE</th>
            <th>SEMESTER</th>
            <th>MAX MARK</th>
            <th>TIME</th>
            <th>DATE</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Data Structures</td>
            <td>CS101</td>
            <td>III</td>
            <td>100</td>
            <td>3 Hrs</td>
            <td>13/05/2026</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div data-type="instruction-block">
      <ol>
        <li>Answer any five questions out of eight.</li>
        <li>All questions carry equal marks.</li>
        <li>Assume suitable data wherever necessary.</li>
      </ol>
    </div>

    <div data-type="section-block">SECTION A</div>

    <div data-type="question-block" data-marks="20" data-number="1">
      <p>Explain the time complexity of QuickSort in best, average, and worst cases. Trace it for the array 10, 7, 8, 9, 1, 5.</p>
    </div>

    <div data-type="question-block" data-marks="20" data-number="2">
      <p>Define a Binary Search Tree. Write algorithms for insertion, deletion, and searching. Construct a BST from 50, 30, 70, 20, 40, 60, 80.</p>
    </div>

    <div data-type="question-group" data-label="Answer any ONE of the following:">
      <div data-type="question-block" data-marks="20" data-number="3">
        <p>(a) Explain Dijkstra's shortest path algorithm with an example. Analyze its time complexity.</p>
      </div>
      <p><strong>OR</strong></p>
      <div data-type="question-block" data-marks="20">
        <p>(b) Explain Kruskal's minimum spanning tree algorithm with a suitable weighted graph.</p>
      </div>
    </div>
  `,

  worksheet: `
    <div data-type="paper-header-block">
      <h1>ALBERT SENIOR SCHOOL</h1>
      <h2>WORKSHEET - ALGEBRA PRACTICE</h2>
      <table>
        <thead>
          <tr>
            <th>SUBJECT</th>
            <th>GRADE</th>
            <th>SET</th>
            <th>MAX MARK</th>
            <th>TIME</th>
            <th>DATE</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Mathematics</td>
            <td>VIII</td>
            <td>A</td>
            <td>20</td>
            <td>45 min</td>
            <td>________</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div data-type="instruction-block">
      <ol>
        <li>Show all steps for full credit.</li>
        <li>Use a pencil for diagrams.</li>
      </ol>
    </div>

    <div data-type="section-block">SECTION A</div>

    <div data-type="question-block" data-marks="2" data-number="1">
      <p>Simplify: 3x + 5x - 2x.</p>
    </div>

    <div data-type="question-block" data-marks="2" data-number="2">
      <p>Solve for x: 2x + 7 = 19.</p>
    </div>
  `,

  competitive: `
    <div data-type="paper-header-block">
      <h1>NATIONAL COMPETITIVE EXAMINATION</h1>
      <h2>GENERAL APTITUDE TEST - 2026</h2>
      <table>
        <thead>
          <tr>
            <th>PAPER</th>
            <th>QUESTIONS</th>
            <th>SET</th>
            <th>MAX MARK</th>
            <th>TIME</th>
            <th>DATE</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Paper I</td>
            <td>100</td>
            <td>A</td>
            <td>200</td>
            <td>2 Hrs</td>
            <td>________</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div data-type="instruction-block">
      <ol>
        <li>Each question carries 2 marks.</li>
        <li>Negative marking: 0.5 marks deducted for each wrong answer.</li>
        <li>No marks are deducted for unanswered questions.</li>
        <li>Use of calculator or mobile phone is prohibited.</li>
      </ol>
    </div>

    <div data-type="section-block">SECTION 1 - ARITHMETIC</div>

    <div data-type="question-block" data-marks="2" data-number="1">
      <p>A train 150 meters long passes a pole in 15 seconds. What is the speed of the train in km/h?</p>
      <ol>
        <li>36</li>
        <li>40</li>
        <li>45</li>
        <li>50</li>
      </ol>
    </div>

    <div data-type="question-block" data-marks="2" data-number="2">
      <p>If the ratio of ages of A and B is 3:5 and the sum of their ages is 64, what is the age of B?</p>
      <ol>
        <li>24</li>
        <li>32</li>
        <li>40</li>
        <li>48</li>
      </ol>
    </div>
  `,
};
